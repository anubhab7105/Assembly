"""Progress event system tests (docs/WORKFLOW.md section 8).

Covers: Pydantic contracts for all 17 event types, sanitization
(no keys / no chain-of-thought), recorder sequencing, disagreement
diffing, DB persistence + ordering, WS replay with ?after_seq=,
the REST fallback, the schema artifact, and a canary secrets scan.
All provider I/O is MockProvider — zero network.
"""

import json
import logging
import time
from typing import Any

import pytest
from fastapi.testclient import TestClient
from pydantic import SecretStr, ValidationError

from src.api.events import (
    PAYLOAD_MODELS,
    EventRecorder,
    ProgressEvent,
    ProgressEventType,
    confidence_label,
    diff_disagreements,
    fetch_events,
    fetch_latest_seq,
    persist_event,
    sanitize_payload,
)

CANARY = "SECRET_CANARY_12345"


def _minimal_payload(event_type: ProgressEventType) -> dict[str, Any]:
    """Smallest valid payload per event type."""
    match event_type:
        case ProgressEventType.EXECUTION_STARTED:
            return {"tier_minutes": 5, "deadline_seconds": 300.0}
        case ProgressEventType.PLAN_READY:
            return {"problem_type": "general", "complexity": "low", "agent_count": 2}
        case ProgressEventType.TEAM_READY:
            return {
                "roles": [
                    {
                        "agent_id": "agent_01",
                        "agent_type": "solver",
                        "model": "m",
                        "provider_name": "p",
                        "role_description": "r",
                        "family": "f",
                    }
                ]
            }
        case ProgressEventType.AGENT_STATUS:
            return {"role": "solver", "activity": "Working", "state": "solving"}
        case ProgressEventType.ROUND_STARTED:
            return {"round": 2, "goal": "Debate round 2"}
        case ProgressEventType.ROUND_FINISHED:
            return {"round": 2, "outcome": "Done"}
        case ProgressEventType.DISAGREEMENT_OPENED:
            return {"description": "a vs b", "agents": ["a", "b"], "round": 2}
        case ProgressEventType.DISAGREEMENT_RESOLVED:
            return {"description": "fixed", "agents": ["a", "b"], "round": 3}
        case ProgressEventType.SOURCE_FOUND | ProgressEventType.SOURCE_VERIFIED:
            return {"title": "T", "domain": "example.com", "url": "https://example.com"}
        case ProgressEventType.CONSENSUS_UPDATED:
            return {
                "score": 0.8,
                "new_info_rate": 0.1,
                "decision": "DEBATE",
                "reason": "keep going",
                "round": 2,
            }
        case ProgressEventType.QUOTA_WARNING:
            return {"provider": "groq", "remaining": 3.0, "detail": "low"}
        case ProgressEventType.TIMER_TICK:
            return {"seconds_remaining": 42.0}
        case ProgressEventType.SYNTHESIS_STARTED:
            return {}
        case ProgressEventType.EXECUTION_COMPLETED:
            return {
                "status": "completed",
                "answer": "42",
                "sources": [],
                "confidence_label": "high",
                "consensus_score": 0.9,
                "agent_count": 2,
                "providers_used": ["groq"],
                "tokens_used": 100,
                "debate_rounds": 1,
                "elapsed_seconds": 12.0,
            }
        case ProgressEventType.EXECUTION_FAILED_PARTIAL:
            return {"status": "failed", "reason": "boom", "answer": ""}
        case ProgressEventType.EXECUTION_CANCELLED:
            return {"status": "cancelled", "reason": "user stop"}
    raise AssertionError(f"unreachable: {event_type}")


# ── Contracts: every event type validates ──────────────────────────


def test_all_seventeen_types_have_models() -> None:
    assert len(ProgressEventType) == 17
    assert set(PAYLOAD_MODELS) == set(ProgressEventType)


def test_minimal_payloads_validate() -> None:
    for event_type in ProgressEventType:
        model = PAYLOAD_MODELS[event_type]
        validated = model.model_validate(_minimal_payload(event_type))
        assert validated.model_dump(exclude_none=False) is not None


def test_invalid_payloads_rejected() -> None:
    with pytest.raises(ValidationError):
        PAYLOAD_MODELS[ProgressEventType.CONSENSUS_UPDATED].model_validate(
            {
                "score": 1.5,
                "new_info_rate": 0,
                "decision": "X",
                "reason": "y",
                "round": 1,
            }
        )
    with pytest.raises(ValidationError):
        PAYLOAD_MODELS[ProgressEventType.PLAN_READY].model_validate(
            {"problem_type": "general", "agent_count": 2}  # complexity missing
        )
    with pytest.raises(ValidationError):
        PAYLOAD_MODELS[ProgressEventType.ROUND_STARTED].model_validate(
            {"round": 0, "goal": "x"}  # rounds start at 1
        )
    with pytest.raises(ValidationError):
        ProgressEvent.model_validate(
            {
                "event_type": "nope.not-real",
                "execution_id": "e",
                "seq": 1,
                "data": {},
            }
        )


def test_confidence_label_bands() -> None:
    assert confidence_label(0.9) == "high"
    assert confidence_label(0.85) == "high"
    assert confidence_label(0.7) == "medium"
    assert confidence_label(0.60) == "medium"
    assert confidence_label(0.59) == "low"
    assert confidence_label(0.0) == "low"


# ── Sanitization: no keys, no CoT ──────────────────────────────────


def test_sanitize_drops_forbidden_keys_nested() -> None:
    payload = {
        "answer": "42",
        "provider_keys": {"groq": CANARY},
        "nested": {"api_key": CANARY, "safe": "kept"},
        "list": [{"authorization": CANARY, "title": "T"}],
        "access_token": CANARY,
    }
    clean = sanitize_payload(payload)
    assert CANARY not in json.dumps(clean)
    assert clean["answer"] == "42"
    assert clean["nested"] == {"safe": "kept"}
    assert clean["list"] == [{"title": "T"}]
    assert "provider_keys" not in clean
    assert "access_token" not in clean


def test_sanitize_replaces_secretstr_and_truncates() -> None:
    long_text = "x" * 5000
    clean = sanitize_payload(
        {
            "key": SecretStr(CANARY),  # forbidden key: dropped entirely
            "note": SecretStr(CANARY),  # allowed key, secret value: masked
            "blob": long_text,
            "model": "gemini-3.8-flash",
        }
    )
    assert CANARY not in json.dumps(clean)
    assert "key" not in clean
    assert clean["note"] == "***"
    assert len(clean["blob"]) <= 2000 + len("…[truncated]")
    assert clean["blob"].endswith("…[truncated]")
    # Benign values survive untouched.
    assert clean["model"] == "gemini-3.8-flash"


def test_sanitize_preserves_benign_counters() -> None:
    payload = {
        "tokens_used": 30,
        "token_fraction_used": 0.5,
        "agent_01": "ok",
        "uid": "123e4567-e89b-12d3-a456-426614174000",
    }
    assert sanitize_payload(payload) == payload


# ── Recorder: dense seqs, validation, replay slice ─────────────────


def test_recorder_assigns_dense_seqs() -> None:
    recorder = EventRecorder("exec-1")
    first = recorder.emit(
        ProgressEventType.EXECUTION_STARTED,
        {"tier_minutes": 3, "deadline_seconds": 180.0},
    )
    second = recorder.emit(
        ProgressEventType.SYNTHESIS_STARTED,
        {},
    )
    assert first["seq"] == 1
    assert second["seq"] == 2
    assert recorder.latest_seq == 2
    assert first["execution_id"] == "exec-1"
    assert "timestamp" in first


def test_recorder_rejects_bad_payload_without_consuming_seq() -> None:
    recorder = EventRecorder("exec-1")
    with pytest.raises(ValidationError):
        recorder.emit(ProgressEventType.TIMER_TICK, {"seconds_remaining": -5})
    assert recorder.latest_seq == 0
    event = recorder.emit(ProgressEventType.TIMER_TICK, {"seconds_remaining": 5})
    assert event["seq"] == 1  # no gap left by the rejected emit


def test_recorder_events_after_slice() -> None:
    recorder = EventRecorder("exec-1")
    for _ in range(5):
        recorder.emit(ProgressEventType.TIMER_TICK, {"seconds_remaining": 1.0})
    assert [e["seq"] for e in recorder.events_after(2)] == [3, 4, 5]
    assert [e["seq"] for e in recorder.events_after(2, limit=2)] == [3, 4]
    assert recorder.events_after(99) == []


# ── Disagreement diffing ───────────────────────────────────────────


def test_diff_opens_resolves_and_truncates() -> None:
    long_position = "p" * 500
    opened, current = diff_disagreements(
        {},
        [
            {
                "agent_id": "agent_01",
                "agent_type": "critic",
                "family": "f",
                "disagrees_with": ["agent_02"],
                "position": long_position,
            }
        ],
        round_number=2,
    )
    assert len(opened) == 1
    event_type, payload = opened[0]
    assert event_type == ProgressEventType.DISAGREEMENT_OPENED
    assert payload["agents"] == ["agent_01", "agent_02"]
    assert len(payload["description"]) <= 500  # position quoted, truncated

    # Stable across rounds: silence.
    opened_again, current = diff_disagreements(
        current,
        [
            {
                "agent_id": "agent_01",
                "agent_type": "critic",
                "family": "f",
                "disagrees_with": ["agent_02"],
                "position": "changed text",
            }
        ],
        round_number=3,
    )
    assert opened_again == []

    # Gone in round 4: resolved.
    resolved, current = diff_disagreements(current, [], round_number=4)
    assert len(resolved) == 1
    assert resolved[0][0] == ProgressEventType.DISAGREEMENT_RESOLVED
    assert "Resolved" in resolved[0][1]["description"]
    assert current == {}


# ── Full mock run: every event validates, dense, clean ─────────────


async def test_mock_run_events_validate_dense_and_clean(orchestrator) -> None:
    events: list[dict[str, Any]] = []

    async def on_progress(event: dict[str, Any]) -> None:
        events.append(event)

    result = await orchestrator.execute(
        execution_id="test-exec-events",
        question="What is the mock answer?",
        time_budget_minutes=3,
        on_progress=on_progress,
    )
    assert result.status == "completed"
    assert events, "expected progress events"

    # Dense sequence starting at 1.
    assert [e["seq"] for e in events] == list(range(1, len(events) + 1))

    # Every event validates against the envelope contract.
    for event in events:
        ProgressEvent.model_validate(event)

    # The §8 lifecycle landmarks are all present.
    names = {e["event_type"] for e in events}
    assert {
        "execution.started",
        "plan.ready",
        "team.ready",
        "consensus.updated",
        "synthesis.started",
        "execution.completed",
    } <= names

    # No secrets, no chain-of-thought, bounded strings — anywhere.
    blob = json.dumps(events)
    for forbidden in (
        "provider_keys",
        "api_key",
        "reasoning_summary",
        "chain_of_thought",
    ):
        assert forbidden not in blob

    def _walk(value: Any) -> None:
        if isinstance(value, dict):
            for item in value.values():
                _walk(item)
        elif isinstance(value, list):
            for item in value:
                _walk(item)
        elif isinstance(value, str):
            assert len(value) <= 2000

    for event in events:
        _walk(event["data"])


# ── Persistence round-trip ─────────────────────────────────────────


def test_persist_fetch_order_and_dedup(db_session) -> None:
    recorder = EventRecorder("exec-db")
    emitted = [
        recorder.emit(
            ProgressEventType.AGENT_STATUS,
            {"role": "solver", "activity": f"step {i}", "state": "solving"},
        )
        for i in range(3)
    ]
    # Insert out of order on purpose: fetch must still return seq order.
    from src.api.events import persist_event as _persist

    assert _persist(db_session, "exec-db", emitted[2]) is True
    assert _persist(db_session, "exec-db", emitted[0]) is True
    assert _persist(db_session, "exec-db", emitted[1]) is True
    # Duplicate seq is ignored, order preserved.
    assert persist_event(db_session, "exec-db", emitted[1]) is False

    rows = fetch_events(db_session, "exec-db")
    assert [row.seq for row in rows] == [1, 2, 3]
    assert fetch_latest_seq(db_session, "exec-db") == 3
    assert fetch_latest_seq(db_session, "nope") == 0
    assert [row.seq for row in fetch_events(db_session, "exec-db", after_seq=2)] == [3]


# ── API: authed client, REST fallback, WS replay, secrets ──────────


def _authed_client(monkeypatch, db_path=None):
    """Desktop local-history client (no accounts, no auth headers)."""
    from sqlalchemy import create_engine as _create_engine
    from sqlalchemy.orm import sessionmaker as _sessionmaker
    from sqlalchemy.pool import StaticPool as _StaticPool

    import src.api.executions as exec_mod
    from src.core.config import settings
    from src.database.base import Base as _Base
    from src.database.base import get_db as _get_db
    from src.main import app

    monkeypatch.setattr(settings, "app_mode", "dev")

    if db_path is None:
        engine = _create_engine(
            "sqlite://",
            connect_args={"check_same_thread": False},
            poolclass=_StaticPool,
        )
    else:
        engine = _create_engine(
            f"sqlite:///{db_path}", connect_args={"check_same_thread": False}
        )
    testing_session = _sessionmaker(bind=engine)
    _Base.metadata.create_all(bind=engine)

    def override_get_db():
        db = testing_session()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[_get_db] = override_get_db
    monkeypatch.setattr(exec_mod, "SessionLocal", testing_session)
    client = TestClient(app)
    return client, ""


def _seed_execution(monkeypatch, question="What is the mock answer?"):
    """Run a full mock execution through the real API and wait for terminal."""
    import src.api.executions as exec_mod
    from src.providers.mock_provider import MockProvider
    from tests.conftest import MockRouter

    client, token = _authed_client(monkeypatch)
    monkeypatch.setattr(
        exec_mod._orchestrator,
        "router",
        MockRouter([MockProvider(provider_name="mock-a")]),
    )
    created = client.post(
        "/api/executions/",
        json={"question": question, "time_budget_minutes": 3},
    )
    assert created.status_code == 200, created.text
    execution_id = created.json()["id"]
    status = ""
    for _ in range(100):
        gotten = client.get(f"/api/executions/{execution_id}")
        assert gotten.status_code == 200
        status = gotten.json()["status"]
        if status in ("completed", "failed"):
            break
        time.sleep(0.2)
    assert status in ("completed", "failed"), f"run never settled: {status}"
    return client, token, execution_id


def _ws_collect(client, token, execution_id, after_seq, want_count):
    """Collect exactly want_count replayed messages, then close.

    Plain blocking receives are safe here: replay rows are sent back to
    back on connect, and the seeded runs are already terminal so no live
    event can interleave. (This starlette's receive_text takes no timeout
    kwarg — a timeout would raise TypeError, not wait.)
    """
    from src.core.config import settings as _settings

    messages: list[dict[str, Any]] = []
    with client.websocket_connect(
        f"/api/executions/ws/{execution_id}?after_seq={after_seq}"
    ) as ws:
        ws.send_text(json.dumps({"type": "auth", "token": _settings.desktop_token}))
        for _ in range(want_count):
            messages.append(json.loads(ws.receive_text()))
    return messages


def _ws_expect_silence(client, token, execution_id, after_seq) -> None:
    """Prove an empty replay: the next message must be our pong, not a row."""
    from src.core.config import settings as _settings

    with client.websocket_connect(
        f"/api/executions/ws/{execution_id}?after_seq={after_seq}"
    ) as ws:
        ws.send_text(json.dumps({"type": "auth", "token": _settings.desktop_token}))
        ws.send_text("ping")
        assert ws.receive_text() == "pong"


def test_rest_events_order_limit_and_latest(monkeypatch) -> None:
    client, _, execution_id = _seed_execution(monkeypatch)

    full = client.get(f"/api/executions/{execution_id}/events")
    assert full.status_code == 200, full.text
    body = full.json()
    events = body["events"]
    assert events, "expected persisted events"
    seqs = [e["seq"] for e in events]
    assert seqs == sorted(seqs)
    assert body["latest_seq"] == max(seqs)
    for event in events:
        ProgressEvent.model_validate(event)

    first_two = client.get(
        f"/api/executions/{execution_id}/events",
        params={"after_seq": 0, "limit": 2},
    ).json()
    assert [e["seq"] for e in first_two["events"]] == seqs[:2]
    assert first_two["latest_seq"] == max(seqs)

    tail = client.get(
        f"/api/executions/{execution_id}/events",
        params={"after_seq": seqs[-1]},
    ).json()
    assert tail["events"] == []
    assert tail["latest_seq"] == max(seqs)


def test_rest_events_missing_is_404(monkeypatch) -> None:
    client, _, _ = _seed_execution(monkeypatch)
    missing = client.get("/api/executions/does-not-exist/events")
    assert missing.status_code == 404


def test_ws_replay_after_seq_and_reconnect(monkeypatch) -> None:
    client, token, execution_id = _seed_execution(monkeypatch)

    total = client.get(f"/api/executions/{execution_id}/events").json()
    seqs = [e["seq"] for e in total["events"]]
    assert len(seqs) >= 3
    latest = total["latest_seq"]
    assert latest == max(seqs)

    # Full replay from scratch, in order.
    all_messages = _ws_collect(client, token, execution_id, 0, len(seqs))
    assert [m["seq"] for m in all_messages] == seqs
    for message in all_messages:
        ProgressEvent.model_validate(message)

    # Suffix replay: mid-log reconnect point.
    mid = len(seqs) // 2
    suffix = _ws_collect(client, token, execution_id, seqs[mid], len(seqs) - mid - 1)
    assert [m["seq"] for m in suffix] == seqs[mid + 1 :]

    # Reconnect with everything seen: silence (no duplicates, no backlog).
    _ws_expect_silence(client, token, execution_id, latest)


def test_events_canary_end_to_end(monkeypatch, tmp_path, caplog) -> None:
    """Reuse the canary: SECRET_CANARY_12345 in no event surface."""

    import src.api.executions as exec_mod
    from src.database.models import ExecutionEvent as ExecutionEventRow

    db_file = tmp_path / "events_canary.db"
    client, token = _authed_client(monkeypatch, str(db_file))

    with caplog.at_level(logging.INFO, logger="assembly"):
        created = client.post(
            "/api/executions/",
            json={
                "question": "What is the mock answer?",
                "time_budget_minutes": 3,
                "provider_keys": {"groq": CANARY},
            },
        )
    assert created.status_code == 200, created.text
    assert CANARY not in created.text
    execution_id = created.json()["id"]

    status = ""
    for _ in range(100):
        gotten = client.get(f"/api/executions/{execution_id}")
        assert gotten.status_code == 200
        status = gotten.json()["status"]
        if status in ("completed", "failed"):
            break
        time.sleep(0.2)
    assert status in ("completed", "failed")

    # REST replay surface.
    replay = client.get(f"/api/executions/{execution_id}/events")
    assert replay.status_code == 200
    assert CANARY not in replay.text

    # WS replay surface.
    latest = replay.json()["latest_seq"]
    ws_messages = _ws_collect(client, token, execution_id, 0, latest)
    assert CANARY not in json.dumps(ws_messages)

    # Raw DB rows + file bytes.
    db = exec_mod.SessionLocal()
    try:
        rows = (
            db.query(ExecutionEventRow)
            .filter(ExecutionEventRow.execution_id == execution_id)
            .all()
        )
        assert CANARY not in json.dumps([row.payload for row in rows])
    finally:
        db.close()
    assert CANARY.encode() not in db_file.read_bytes()
    assert CANARY not in caplog.text


# ── Schema artifact + OpenAPI ───────────────────────────────────────


def test_schema_bundle_covers_all_types() -> None:
    from src.api.events import event_schema_bundle as bundle_fn

    bundle = bundle_fn()
    assert bundle["version"] == 1
    assert len(bundle["event_types"]) == 17
    assert set(bundle["payloads"]) == set(bundle["event_types"])
    assert set(bundle["envelope"]["properties"]) == {
        "event_type",
        "execution_id",
        "seq",
        "state",
        "data",
        "timestamp",
    }


def test_export_script_writes_artifact(tmp_path) -> None:
    import subprocess
    import sys

    out = tmp_path / "event-schema.json"
    completed = subprocess.run(
        [sys.executable, "scripts/export_event_schema.py", "--out", str(out)],
        capture_output=True,
        text=True,
        check=False,
        cwd=str(__import__("pathlib").Path(__file__).resolve().parent.parent),
    )
    assert completed.returncode == 0, completed.stderr
    artifact = json.loads(out.read_text(encoding="utf-8"))
    assert len(artifact["event_types"]) == 17


def test_openapi_exposes_event_models(monkeypatch) -> None:
    client, _ = _authed_client(monkeypatch)
    spec = client.get("/openapi.json")
    assert spec.status_code == 200
    body = spec.json()
    assert "/api/executions/{execution_id}/events" in body["paths"]
    assert "ProgressEvent" in body["components"]["schemas"]
    assert "EventListResponse" in body["components"]["schemas"]
