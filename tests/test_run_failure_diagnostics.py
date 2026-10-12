"""P0 regression: blank Assembly runs must surface safe failure diagnostics.

Covers:
- orchestrator exception before any agent exists (stage orchestrator_start)
- run that fails after initial progress (stage = last lifecycle state)
- failed ExecutionResult (no exception) still carries diagnostics
- router-construction and orchestrator-construction failures inside the
  protected init block (stages router_init / orchestrator_init)
- successful run returns completed + final answer with no error fields
- key secrecy: canary never appears in logs or SSE, even when the
  raw exception message contains it
"""

import asyncio
import logging

import pytest

#: Synthetic test marker. Deliberately not credential-shaped (no ``sk-``
#: prefix, no high-entropy token) so secret scanners stay quiet; the tests
#: still assert it never appears in logs or SSE events.
CANARY_KEY = "TEST-ONLY-CANARY-NOT-A-REAL-CREDENTIAL"
CANARY_QUESTION = "Canary rundiag ZULU-77: why do hummingbirds hum?"


def _drain(entry):
    events = []
    while True:
        try:
            item = entry.queue.get_nowait()
        except asyncio.QueueEmpty:
            break
        if item is None:
            break
        events.append(item)
    return events


def _finished(events):
    finals = [e for e in events if e.get("event_type") == "run.finished"]
    assert len(finals) == 1, f"expected one run.finished, got {events}"
    return finals[0]


async def _run_with_orch(monkeypatch, orch_behavior):
    """Run _execute_run with a stubbed Orchestrator. Returns (events, entry)."""
    import src.api.run as run_mod
    import src.orchestration.orchestrator as orch_mod

    class StubOrch:
        def __init__(self):
            self.router = None

        async def execute(self, **kwargs):
            return await orch_behavior(kwargs.get("on_progress"))

    monkeypatch.setattr(orch_mod, "Orchestrator", StubOrch)

    entry = run_mod._RunEntry(run_id="run-diag-123abc", created_at=run_mod._now())
    await run_mod._execute_run(
        "run-diag-123abc",
        CANARY_QUESTION,
        3,
        {"groq": CANARY_KEY},
        set(),
        {},
        [],
        entry,
        search_keys=None,
        router_override=object(),
    )
    return _drain(entry), entry


@pytest.mark.asyncio()
async def test_orchestrator_exception_before_agents_has_diagnostics(
    monkeypatch, caplog
):
    async def boom(on_progress):
        raise RuntimeError("No usable model family for this run")

    with caplog.at_level(logging.INFO, logger="assembly"):
        events, _ = await _run_with_orch(monkeypatch, boom)

    fin = _finished(events)
    assert fin["run_id"] == "run-diag-123abc"
    assert fin["status"] == "failed"
    assert fin["stage"] == "orchestrator_start"
    assert fin["error_class"] == "RuntimeError"
    assert fin["error_code"] == "no_usable_models"
    assert "Check your provider keys" in fin["message"]
    blob = str(events)
    assert CANARY_KEY not in blob
    assert CANARY_KEY not in caplog.text
    assert CANARY_QUESTION not in caplog.text
    # Raw exception messages never reach logs or SSE.
    assert "No usable model family" not in caplog.text
    assert "No usable model family" not in blob


@pytest.mark.asyncio()
async def test_run_fails_after_initial_progress_keeps_stage(monkeypatch, caplog):
    async def boom_late(on_progress):
        await on_progress(
            {"event_type": "execution.started", "state": "planning", "data": {}}
        )
        await on_progress(
            {"event_type": "agent.status", "state": "planning", "data": {}}
        )
        # Raw message carries a credential: must never leak.
        raise ValueError(f"bad state with key {CANARY_KEY} inside")

    with caplog.at_level(logging.INFO, logger="assembly"):
        events, _ = await _run_with_orch(monkeypatch, boom_late)

    fin = _finished(events)
    assert fin["status"] == "failed"
    assert fin["stage"] == "planning"
    assert fin["error_class"] == "ValueError"
    assert fin["error_code"] == "invalid_state"
    blob = str(events)
    assert CANARY_KEY not in blob
    assert CANARY_KEY not in caplog.text


@pytest.mark.asyncio()
async def test_failed_result_without_exception_still_diagnostic(monkeypatch, caplog):
    from src.orchestration.orchestrator import ExecutionResult

    async def fail_result(on_progress):
        await on_progress(
            {"event_type": "execution.started", "state": "solving", "data": {}}
        )
        return ExecutionResult(
            answer="",
            sources=[],
            consensus_score=0.0,
            problem_type="unknown",
            complexity="unknown",
            agent_count=0,
            debate_rounds=0,
            total_tokens=0,
            status="failed",
        )

    with caplog.at_level(logging.INFO, logger="assembly"):
        events, _ = await _run_with_orch(monkeypatch, fail_result)

    fin = _finished(events)
    assert fin["status"] == "failed"
    assert fin["stage"] == "solving"
    assert fin["error_code"] == "execution_failed"
    assert fin["error_class"] == "ExecutionResult"
    assert CANARY_KEY not in str(events)
    assert CANARY_KEY not in caplog.text


@pytest.mark.asyncio()
async def test_successful_run_returns_completed_without_error_fields(monkeypatch):
    from src.orchestration.orchestrator import ExecutionResult

    seen = []

    async def ok(on_progress):
        evt = {"event_type": "execution.started", "state": "planning", "data": {}}
        seen.append(evt)
        await on_progress(evt)
        return ExecutionResult(
            answer="The team concludes 42.",
            sources=[],
            consensus_score=0.8,
            problem_type="general",
            complexity="medium",
            agent_count=3,
            debate_rounds=1,
            total_tokens=100,
            status="completed",
        )

    events, _ = await _run_with_orch(monkeypatch, ok)
    fin = _finished(events)
    assert fin["status"] == "completed"
    assert "error_code" not in fin
    assert "error_class" not in fin
    assert fin["usage"] != []


def test_failure_code_mapping_sanitizes_class_names():
    import src.api.run as run_mod

    assert run_mod._failure_code_for(RuntimeError("x")) == "runtime_error"
    assert run_mod._failure_code_for(ValueError("x")) == "invalid_state"

    class WeirdError(Exception):
        pass

    WeirdError.__name__ = "WeirdError; DROP TABLE"
    code = run_mod._failure_code_for(WeirdError("boom"))
    assert code == "weirderror_drop_table"
    assert run_mod._sanitized_code("") == "internal_error"


@pytest.mark.asyncio()
async def test_router_construction_failure_finishes_run(monkeypatch, caplog):
    """A router-init raise still ends the stream with run.finished failed."""
    import src.api.run as run_mod

    def _boom(provider_keys, allowed, pins):
        raise RuntimeError(f"router boom with marker {CANARY_KEY} inside")

    monkeypatch.setattr(run_mod, "_filtered_router", _boom)

    entry = run_mod._RunEntry(run_id="run-diag-router", created_at=run_mod._now())
    with caplog.at_level(logging.INFO, logger="assembly"):
        await run_mod._execute_run(
            "run-diag-router",
            CANARY_QUESTION,
            3,
            {"groq": CANARY_KEY},
            set(),
            {},
            [],
            entry,
            search_keys=None,
            router_override=None,
        )
    events = _drain(entry)
    assert entry.done is True
    fin = _finished(events)
    assert fin["run_id"] == "run-diag-router"
    assert fin["status"] == "failed"
    assert fin["stage"] == "router_init"
    assert fin["error_class"] == "RuntimeError"
    assert "Check your provider keys" in fin["message"]
    blob = str(events)
    assert CANARY_KEY not in blob
    assert CANARY_KEY not in caplog.text


@pytest.mark.asyncio()
async def test_orchestrator_construction_failure_finishes_run(monkeypatch, caplog):
    """An Orchestrator() raise still ends the stream with run.finished failed."""
    import src.api.run as run_mod
    import src.orchestration.orchestrator as orch_mod

    class BoomOrch:
        def __init__(self):
            raise ConnectionError(f"orchestrator boom {CANARY_KEY}")

    monkeypatch.setattr(orch_mod, "Orchestrator", BoomOrch)

    entry = run_mod._RunEntry(run_id="run-diag-orch", created_at=run_mod._now())
    with caplog.at_level(logging.INFO, logger="assembly"):
        await run_mod._execute_run(
            "run-diag-orch",
            CANARY_QUESTION,
            3,
            {"groq": CANARY_KEY},
            set(),
            {},
            [],
            entry,
            search_keys=None,
            router_override=object(),
        )
    events = _drain(entry)
    assert entry.done is True
    fin = _finished(events)
    assert fin["run_id"] == "run-diag-orch"
    assert fin["status"] == "failed"
    assert fin["stage"] == "orchestrator_init"
    assert fin["error_class"] == "ConnectionError"
    assert fin["error_code"] == "provider_unavailable"
    blob = str(events)
    assert CANARY_KEY not in blob
    assert CANARY_KEY not in caplog.text
