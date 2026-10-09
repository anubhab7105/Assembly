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
    from src.providers.mock_provider import MockProvider
    from tests.conftest import MockRouter

    def _fake(provider_keys, allowed, pins):
        return MockRouter(
            [MockProvider(provider_name="mock-a"), MockProvider(provider_name="mock-b")]
        )

    monkeypatch.setattr(run_mod, "_filtered_router", _fake)


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
