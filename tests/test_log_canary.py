"""Logging canary: SECRET_CANARY_12345 must appear in no log, DB file,
API response, WebSocket-shaped event, or exception text.

The canary travels only where keys travel (request provider_keys, env).
The live WebSocket layer is a verbatim relay of on_progress payloads
(src/api/executions.py::_run_execution json.dumps each event), so the
deterministic guarantee comes from capturing those exact payloads, plus
a best-effort live WebSocket collection.
"""

import json
import logging
import time
from typing import Any

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from src.core.config import settings
from src.core.keystore import RequestKeyStore
from src.core.logging_config import KeyMaskingFilter, logger, mask_text
from src.database.base import Base, get_db
from src.orchestration.orchestrator import Orchestrator

CANARY = "SECRET_CANARY_12345"


# ── Filter unit tests ─────────────────────────────────────────────────


def test_mask_known_prefixes() -> None:
    assert "AIza" not in mask_text("key=AIzaSyD-1234567890abcdefghij")
    assert "gsk_" not in mask_text("gsk_abcdefghij1234567890")
    assert "sk-or-" not in mask_text("sk-or-v1-abcdef1234567890")
    assert "hf_" not in mask_text("hf_abcdefghij1234567890")


def test_mask_sensitive_fields() -> None:
    assert CANARY not in mask_text(f'{{"api_key": "{CANARY}"}}')
    assert CANARY not in mask_text(f"api_key={CANARY}")
    assert CANARY not in mask_text(f"provider_keys={{'groq': '{CANARY}'}}")
    assert "***" in mask_text(f'{{"api_key": "{CANARY}"}}')


def test_mask_headers() -> None:
    assert CANARY not in mask_text(f"Authorization: Bearer {CANARY}")
    assert CANARY not in mask_text(f"x-api-key: {CANARY}")
    assert "Bearer" not in mask_text(f"Authorization: Bearer {CANARY}")


def test_mask_leaves_benign_text_alone() -> None:
    assert mask_text("tokens_used: 30") == "tokens_used: 30"
    assert mask_text("token_fraction_used: 0.5") == "token_fraction_used: 0.5"
    assert mask_text("agent_01") == "agent_01"
    assert "gemini-3.8-flash" in mask_text("model gemini-3.8-flash live")
    uid = "123e4567-e89b-12d3-a456-426614174000"
    assert mask_text(uid) == uid  # UUIDs (36 chars) are not key-shaped


def test_mask_leaves_git_commit_shas_alone() -> None:
    sha = "0123456789abcdef0123456789abcdef01234567"
    line = f"git log --oneline {sha}"
    assert sha in mask_text(line)
    assert "git log --oneline" in mask_text(line)


def test_filter_applies_to_assembly_logs(caplog) -> None:
    with caplog.at_level(logging.INFO, logger="assembly"):
        logger.info("provider error for api_key=%s", CANARY)
        logger.info("Authorization: Bearer %s", CANARY)
    assert CANARY not in caplog.text
    assert "***" in caplog.text


def test_filter_applies_to_third_party_loggers(caplog) -> None:
    with caplog.at_level(logging.DEBUG):
        logging.getLogger("httpx").info("sending x-api-key: %s", CANARY)
    assert CANARY not in caplog.text


def test_filter_is_attached() -> None:
    assert any(isinstance(f, KeyMaskingFilter) for f in logger.filters)
    assert any(isinstance(f, KeyMaskingFilter) for f in logging.getLogger().filters)


# ── Full execution canary (MockProvider paths) ────────────────────────


async def test_canary_absent_in_success_path(orchestrator, monkeypatch, caplog) -> None:
    monkeypatch.setenv("GEMINI_API_KEY", CANARY)
    store = RequestKeyStore({"groq": CANARY})
    events: list[dict[str, Any]] = []

    async def on_progress(event: dict[str, Any]) -> None:
        events.append(event)

    workspace_seen: list[str] = []
    from src.orchestration.workspace import workspace

    async def listener(event) -> None:
        workspace_seen.append(json.dumps(event.to_dict()))

    execution_id = "canary-success"
    workspace.subscribe(execution_id, listener)
    try:
        with caplog.at_level(logging.INFO, logger="assembly"):
            result = await orchestrator.execute(
                execution_id=execution_id,
                question="What is the mock answer?",
                time_budget_minutes=3,
                on_progress=on_progress,
            )
    finally:
        store.clear()
        workspace.cleanup(execution_id)

    assert result.status == "completed"
    assert store.get_keys() == {}
    assert CANARY not in caplog.text
    assert CANARY not in json.dumps(events)
    assert CANARY not in result.answer + json.dumps(result.sources)
    assert CANARY not in "".join(workspace_seen)
    assert any(e["event_type"] == "execution.completed" for e in events)


async def test_canary_absent_in_failure_path_events(caplog) -> None:
    """One live key: routing fails, error event + answer must stay generic."""
    from src.providers.router import ModelRouter

    orch = Orchestrator()
    orch.router = ModelRouter(keys={"groq": CANARY})
    events: list[dict[str, Any]] = []

    async def on_progress(event: dict[str, Any]) -> None:
        events.append(event)

    with caplog.at_level(logging.INFO, logger="assembly"):
        result = await orch.execute(
            execution_id="canary-failure",
            question="What is the mock answer?",
            time_budget_minutes=3,
            on_progress=on_progress,
        )

    assert result.status == "failed"
    assert (
        result.answer
        == "An error occurred while processing your question. Please try again."
    )
    assert CANARY not in caplog.text
    assert CANARY not in json.dumps(events)
    error_events = [e for e in events if e["event_type"] == "execution.failed_partial"]
    assert error_events != []
    assert all("server logs" in e["data"]["reason"] for e in error_events)


# ── API canary (TestClient + SQLite FILE bytes) ───────────────────────


def _authed_client(monkeypatch, db_path: str) -> tuple[TestClient, str]:
    import src.api.executions as exec_mod
    from src.main import app

    engine = create_engine(
        f"sqlite:///{db_path}", connect_args={"check_same_thread": False}
    )
    testing_session = sessionmaker(bind=engine)
    Base.metadata.create_all(bind=engine)

    def override_get_db():
        db = testing_session()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = override_get_db
    monkeypatch.setattr(exec_mod, "SessionLocal", testing_session)
    client = TestClient(app)
    signup = client.post(
        "/api/auth/signup",
        json={
            "email": "canary@test.local",
            "name": "Canary",
            "password": "password123",
        },
    )
    assert signup.status_code == 200, signup.text
    token = signup.json()["access_token"]
    client.headers.update({"Authorization": f"Bearer {token}"})
    return client, token


def test_canary_end_to_end_api_db_ws(monkeypatch, tmp_path, caplog) -> None:
    db_file = tmp_path / "canary.db"
    client, token = _authed_client(monkeypatch, str(db_file))

    with caplog.at_level(logging.INFO, logger="assembly"):
        # One key on purpose: routing fails before any network I/O, so the
        # run is fast and hermetic. (Multi-key runs attempt real connections
        # and, under TestClient's per-request portals, the background task
        # can outlive the test's polling window — a test-harness artifact,
        # not product code; the success/failure on_progress tests above
        # cover the event shapes deterministically.)
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

    # Best-effort live WebSocket collection (the run fails fast offline,
    # so the socket may attach after completion — the deterministic
    # coverage is the on_progress payload capture above).
    ws_messages: list[str] = []
    try:
        with client.websocket_connect(
            f"/api/executions/ws/{execution_id}"
        ) as ws:
            ws.send_text(json.dumps({"type": "auth", "token": token}))
            deadline = time.monotonic() + 8.0
            while time.monotonic() < deadline:
                try:
                    message = ws.receive_text(timeout=1.0)
                except Exception:  # noqa: BLE001 — best-effort drain ends on any failure
                    break
                ws_messages.append(message)
                data = json.loads(message)
                if data.get("event_type") in (
                    "execution.completed",
                    "execution.failed_partial",
                ):
                    break
    except Exception:  # noqa: BLE001, S110 — no socket yet means nothing to scan
        pass

    status = ""
    for _ in range(100):
        gotten = client.get(f"/api/executions/{execution_id}")
        assert gotten.status_code == 200
        status = gotten.json()["status"]
        if status in ("completed", "failed"):
            break
        time.sleep(0.2)
    assert status in ("completed", "failed")

    assert CANARY not in gotten.text
    assert "provider_keys" not in gotten.json()
    assert CANARY not in "".join(ws_messages)
    assert CANARY not in caplog.text
    # The raw database FILE bytes (not just ORM rows).
    assert CANARY.encode() not in db_file.read_bytes()


def test_canary_absent_in_422(monkeypatch, tmp_path) -> None:
    client, _ = _authed_client(monkeypatch, str(tmp_path / "canary422.db"))
    response = client.post(
        "/api/executions/",
        json={
            "question": "",
            "time_budget_minutes": 3,
            "provider_keys": {"groq": CANARY},
        },
    )
    assert response.status_code == 422
    assert response.json() == {"detail": "Invalid request."}
    assert CANARY not in response.text


def test_providers_status_hides_mode_keys() -> None:
    import uuid

    from fastapi.testclient import TestClient as TC

    from src.main import app

    client = TC(app)
    signup = client.post(
        "/api/auth/signup",
        json={
            "email": f"canary-{uuid.uuid4().hex[:8]}@test.local",
            "name": "Canary",
            "password": "password123",
        },
    )
    client.headers.update({"Authorization": f"Bearer {signup.json()['access_token']}"})
    response = client.get("/api/providers/status")
    assert response.status_code == 200
    for attr in (
        "gemini_api_key",
        "groq_api_key",
        "cerebras_api_key",
        "openrouter_api_key",
        "huggingface_api_key",
        "tavily_api_key",
        "jwt_secret_key",
    ):
        value = getattr(settings, attr).get_secret_value()
        if value:
            assert value not in response.text
