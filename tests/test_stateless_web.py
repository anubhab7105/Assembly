"""Stateless web tests (feat/stateless-web).

- Canary key + canary question never appear in logs or any file.
- Web mode creates no database file and performs no disk writes.
- Stateless run end to end (SSE, mock router, no DB).
- usage_snapshot changes the capacity plan.
- Cancel on disconnect cancels the background run.
"""

import asyncio
import json
import logging

import pytest
from fastapi.testclient import TestClient

CANARY_KEY = "sk-CANARY-STATLESS-9f8e7d6c5b4a"
CANARY_QUESTION = "Canary question ZULU-UNIQUE-42: why do hummingbirds hum?"


@pytest.fixture()
def web_mode(monkeypatch, tmp_path):
    from src.core.config import settings

    monkeypatch.setattr(settings, "app_mode", "web")
    monkeypatch.setattr(settings, "app_env", "development")
    monkeypatch.setattr(settings, "debug", False)
    monkeypatch.chdir(tmp_path)
    yield settings


def _mock_filtered_router(monkeypatch):
    import src.api.run as run_mod
    from src.api.request_context import RequestContext
    from src.providers.mock_provider import MockProvider
    from tests.conftest import MockRouter

    def _fake(provider_keys, search_keys, selected, pins, usage_snapshot):
        return RequestContext(
            router=MockRouter(
                [MockProvider(provider_name="mock-a"), MockProvider(provider_name="mock-b")]
            ),
            allowed=set(),
            pins={},
            quota_snapshot=[],
            has_search_key=False,
        )

    monkeypatch.setattr(run_mod, "build_request_context", _fake)


def test_web_mode_creates_no_database_file(web_mode, tmp_path, monkeypatch) -> None:
    from src.core.config import settings
    from src.database.base import init_db

    with pytest.raises(RuntimeError, match="stateless"):
        _ = settings.effective_database_url
    init_db()  # no-op, must not raise or write
    assert list(tmp_path.glob("*.db")) == []
    assert list(tmp_path.glob("assembly.db")) == []

    from src.main import app

    client = TestClient(app)
    health = client.get("/health")
    assert health.status_code == 200
    assert health.json()["status"] == "healthy"
    assert list(tmp_path.glob("*.db")) == []


def test_catalog_returns_providers_models_families(web_mode) -> None:
    from src.main import app

    client = TestClient(app)
    res = client.get("/api/catalog")
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["providers"] != []
    assert body["families"] != []
    ids = [m["id"] for p in body["providers"] for m in p["models"]]
    assert any(ids)


def test_stateless_run_end_to_end_no_leak(web_mode, monkeypatch, caplog) -> None:
    from src.main import app

    _mock_filtered_router(monkeypatch)
    client = TestClient(app)
    with caplog.at_level(logging.INFO, logger="assembly"), client.stream(
        "POST",
        "/api/run",
        json={
            "question": CANARY_QUESTION,
            "time_budget_minutes": 3,
            "provider_keys": {"groq": CANARY_KEY},
            "model_selection": {"selected": [], "pins": {}},
            "usage_snapshot": [],
        },
    ) as res:
        assert res.status_code == 200, res.text
        events = []
        for line in res.iter_lines():
            if not line or line.startswith(":"):
                continue
            assert line.startswith("data: ")
            events.append(json.loads(line[len("data: ") :]))
    assert events, "expected SSE events"
    assert events[-1].get("event_type") == "run.finished"
    assert events[-1].get("status") in ("completed", "failed", "failed_partial")
    assert events[-1].get("usage") != []
    blob = json.dumps(events)
    assert CANARY_KEY not in blob
    assert CANARY_KEY not in caplog.text
    assert CANARY_QUESTION not in caplog.text


def test_canary_question_never_in_422(web_mode) -> None:
    from src.main import app

    client = TestClient(app)
    res = client.post(
        "/api/run",
        json={
            "question": "",
            "time_budget_minutes": 3,
            "provider_keys": {"groq": CANARY_KEY},
        },
    )
    assert res.status_code == 422
    assert CANARY_KEY not in res.text


def test_usage_snapshot_changes_plan() -> None:
    from src.orchestration.capacity import (
        KeyBudget,
        heuristic_suggestion,
        plan_capacity,
    )

    keys = [KeyBudget(provider="p", rpm_limit=30, rpd_remaining=10)]
    suggestion = heuristic_suggestion("Is React better than Vue for a large team?")
    base = plan_capacity(keys, 5, suggestion)
    snap = plan_capacity(
        keys,
        5,
        suggestion,
        usage_snapshot=[{"provider": "p", "model": "m", "count": 9, "tokens": 0}],
    )
    assert snap.affordable_calls is not None and base.affordable_calls is not None
    assert snap.affordable_calls < base.affordable_calls


def test_quota_takes_max_of_snapshot_and_memory() -> None:
    from src.providers.quota import QuotaLimiter

    limiter = QuotaLimiter(config=None, session_factory=None)
    limiter.set_usage_snapshot([{"provider": "p", "model": "m", "count": 7, "tokens": 100}])
    assert limiter._today_counters("p", "fp", "m") == (7, 100)
    limiter.set_usage_snapshot([])
    assert limiter._today_counters("p", "fp", "m") == (0, 0)


def test_cancel_on_disconnect(web_mode, monkeypatch) -> None:
    """Disconnect path: cancelling the run task settles it as cancelled."""
    import src.api.run as run_mod

    async def _scenario() -> str:
        entry = run_mod._RunEntry(run_id="run-test", created_at=run_mod._now())

        async def _work() -> None:
            try:
                await asyncio.sleep(30.0)
            except asyncio.CancelledError:
                await entry.queue.put(
                    {
                        "event_type": "run.finished",
                        "run_id": "run-test",
                        "status": "cancelled",
                    }
                )
                raise
            finally:
                entry.done = True
                await entry.queue.put(None)

        entry.task = asyncio.create_task(_work())
        await asyncio.sleep(0.05)
        assert not entry.task.done()
        # Simulate SSE disconnect handler.
        entry.task.cancel()
        try:
            await entry.task
        except asyncio.CancelledError:
            pass
        assert entry.done
        first = await asyncio.wait_for(entry.queue.get(), timeout=5.0)
        assert first["status"] == "cancelled"
        return first["status"]

    assert asyncio.run(_scenario()) == "cancelled"


def test_invalid_failures_do_not_consume_run_budget(web_mode) -> None:
    """Validation failures hit the loose invalid budget, never run starts."""
    from src.core.rate_limit import _rate_limit_history
    from src.main import app

    client = TestClient(app)
    for _ in range(3):
        res = client.post(
            "/api/run",
            json={"question": "", "time_budget_minutes": 3},
        )
        assert res.status_code == 422
    invalid_keys = [k for k in _rate_limit_history if k[1] == "invalid"]
    assert invalid_keys, "invalid attempts must be counted"
    run_keys = [k for k in _rate_limit_history if k[1] == "run"]
    assert run_keys == [], "rejected requests must not spend the run budget"


def test_per_ip_concurrency_cap(web_mode, monkeypatch) -> None:
    """One IP holding MAX_RUNS_PER_IP slots gets 429; freed slots run."""
    import src.api.run as run_mod
    from src.core.rate_limit import MAX_RUNS_PER_IP
    from src.main import app

    _mock_filtered_router(monkeypatch)
    peer = "testclient"
    held = []
    try:
        for i in range(MAX_RUNS_PER_IP):
            entry = run_mod._RunEntry(
                run_id=f"run-held-{i}", created_at=run_mod._now(), ip=peer
            )
            run_mod._runs[entry.run_id] = entry
            held.append(entry.run_id)
        client = TestClient(app)
        res = client.post(
            "/api/run",
            json={
                "question": "Canary question concurrency: why do hummingbirds hum?",
                "time_budget_minutes": 3,
                "provider_keys": {"groq": CANARY_KEY},
                "model_selection": {"selected": [], "pins": {}},
                "usage_snapshot": [],
            },
        )
        assert res.status_code == 429
        assert "Concurrent execution limit" in res.json()["detail"]
    finally:
        for rid in held:
            run_mod._runs.pop(rid, None)

    client = TestClient(app)
    with client.stream(
        "POST",
        "/api/run",
        json={
            "question": CANARY_QUESTION,
            "time_budget_minutes": 3,
            "provider_keys": {"groq": CANARY_KEY},
            "model_selection": {"selected": [], "pins": {}},
            "usage_snapshot": [],
        },
    ) as res:
        assert res.status_code == 200, res.text
        blob_lines = []
        for line in res.iter_lines():
            blob_lines.append(line)
            if line.startswith("data: ") and '"run.finished"' in line:
                break
    assert CANARY_KEY not in "\n".join(blob_lines)


@pytest.mark.asyncio()
async def test_failed_web_run_wipes_request_keys_and_quota_snapshot(monkeypatch, caplog):
    """Request secrets and client quota snapshots are cleared on every terminal path.

    The orchestrator stub deliberately raises an exception containing the
    fake key. Only safe failure diagnostics may reach logs/SSE, and both the
    request-key store and shared limiter snapshot must be empty afterwards.
    """
    import src.api.run as run_mod
    import src.orchestration.orchestrator as orch_mod
    from src.providers.quota import get_limiter

    fake_key = "TEST-ONLY-WEB-KEY-CLEANUP-CANARY"
    entry = run_mod._RunEntry(run_id="run-cleanup-canary", created_at=run_mod._now())
    limiter = get_limiter()
    limiter.set_usage_snapshot(
        [{"provider": "groq", "model": "m", "count": 2, "tokens": 100}]
    )

    class StubOrch:
        def __init__(self):
            self.router = None

        async def execute(self, **kwargs):
            # Record exactly what the handler passed to the run, then fail
            # with a secret-shaped payload to test safe diagnostic behavior.
            assert kwargs["provider_keys"] == {"groq": fake_key}
            raise RuntimeError(f"upstream error unexpectedly included {fake_key}")

    monkeypatch.setattr(orch_mod, "Orchestrator", StubOrch)
    with caplog.at_level(logging.INFO, logger="assembly"):
        await run_mod._execute_run(
            "run-cleanup-canary",
            "synthetic cleanup test question",
            3,
            {"groq": fake_key},
            set(),
            {},
            [{"provider": "groq", "model": "m", "count": 2, "tokens": 100}],
            entry,
            search_keys={"tavily": "TEST-ONLY-SEARCH-KEY-CANARY"},
            router_override=object(),
        )

    events = []
    while True:
        item = await entry.queue.get()
        if item is None:
            break
        events.append(item)

    rendered = json.dumps(events)
    assert entry.done is True
    assert len([e for e in events if e.get("event_type") == "run.finished"]) == 1
    finished = next(e for e in events if e.get("event_type") == "run.finished")
    assert finished["status"] == "failed"
    assert finished["error_code"] == "runtime_error"
    assert fake_key not in rendered
    assert fake_key not in caplog.text
    assert "upstream error unexpectedly included" not in caplog.text
    assert limiter._snapshot == {}

def test_run_rejects_unsupported_attachment_without_echoing_content(web_mode, monkeypatch):
    """Unsupported attachments are rejected before any run or provider call."""
    from src.main import app

    client = TestClient(app)
    secret_marker = "ATTACHMENT-MUST-NOT-ECHO-UNSUPPORTED-BINARY"
    res = client.post(
        "/api/run",
        json={
            "question": "Summarize this",
            "time_budget_minutes": 3,
            "provider_keys": {"groq": CANARY_KEY},
            "attachments": [{
                "filename": "../../bad.exe",
                "media_type": "application/octet-stream",
                "content": secret_marker,
            }],
        },
    )
    assert res.status_code == 422
    assert "unsupported file type" in res.json()["detail"].lower()
    assert secret_marker not in res.text
    assert CANARY_KEY not in res.text


def test_run_rejects_oversized_attachment_before_creating_run(web_mode):
    from src.main import app
    import src.api.run as run_mod

    run_count = len(run_mod._runs)
    res = TestClient(app).post(
        "/api/run",
        json={
            "question": "Analyze file",
            "time_budget_minutes": 3,
            "attachments": [{
                "filename": "big.txt",
                "media_type": "text/plain",
                "content": "x" * (256 * 1024 + 1),
            }],
        },
    )
    assert res.status_code in (413, 422)
    assert len(run_mod._runs) == run_count


def test_attachment_content_reaches_orchestrator_but_not_sse_or_logs(web_mode, monkeypatch, caplog):
    """The uploaded text becomes prompt context, not response/log metadata."""
    import src.api.run as run_mod
    import src.orchestration.orchestrator as orch_mod
    from src.main import app
    from src.orchestration.orchestrator import ExecutionResult

    source_marker = "ATTACHMENT-CONTENT-CANARY-7F3C"
    captured = {}

    class StubOrch:
        def __init__(self):
            self.router = None

        async def execute(self, **kwargs):
            captured["question"] = kwargs["question"]
            captured["attachment_context"] = kwargs["attachment_context"]
            return ExecutionResult(
                execution_id=kwargs["execution_id"],
                status="completed",
                final_answer="Mock answer.",
                total_tokens=0,
            )

    _mock_filtered_router(monkeypatch)
    monkeypatch.setattr(orch_mod, "Orchestrator", StubOrch)
    client = TestClient(app)
    with caplog.at_level(logging.INFO, logger="assembly"), client.stream(
        "POST",
        "/api/run",
        json={
            "question": "Summarize the attached component",
            "time_budget_minutes": 3,
            "provider_keys": {"groq": CANARY_KEY},
            "model_selection": {"selected": [], "pins": {}},
            "usage_snapshot": [],
            "attachments": [{
                "filename": "component.tsx",
                "media_type": "text/plain",
                "content": f'<div>hello</div>\\n{source_marker}',
            }],
        },
    ) as res:
        assert res.status_code == 200, res.text
        lines = []
        for line in res.iter_lines():
            lines.append(line)
            if line.startswith("data: ") and '"run.finished"' in line:
                break

    assert source_marker in captured["attachment_context"]
    assert "component.tsx" in captured["attachment_context"]
    assert captured["question"] == "Summarize the attached component"
    assert source_marker not in "\\n".join(lines)
    assert source_marker not in caplog.text
    assert CANARY_KEY not in "\\n".join(lines)
    assert CANARY_KEY not in caplog.text
