"""End-to-end orchestrator execution using only MockProvider (zero network)."""

import asyncio
from typing import Any

from src.orchestration.orchestrator import Orchestrator
from src.orchestration.workspace import EventType, WorkspaceEvent, workspace
from src.providers.mock_provider import MockProvider


async def test_full_execution_end_to_end(orchestrator: Orchestrator) -> None:
    events: list[dict[str, Any]] = []

    async def on_progress(event: dict[str, Any]) -> None:
        events.append(event)

    result = await orchestrator.execute(
        execution_id="test-exec-e2e",
        question="What is the mock answer?",
        time_budget_minutes=3,
        on_progress=on_progress,
    )

    # A final answer is produced.
    assert result.status == "completed"
    assert "FINAL MOCK ANSWER" in result.answer
    assert result.agent_count == 2
    assert result.debate_rounds >= 1
    assert 0.0 <= result.consensus_score <= 1.0

    # Tokens are tracked: every mock call reports 30 tokens, planner
    # included (the planner is a real quota-consuming call; excluding it
    # undercounted each run and broke tpm accounting).
    providers: list[MockProvider] = list(orchestrator.router._providers.values())
    total_calls = sum(len(p.calls) for p in providers)
    assert total_calls > 0
    assert result.total_tokens == total_calls * 30
    assert any(
        entry.get("stage") == "planner" for entry in (result.call_log or [])
    )

    # Events are published to the progress callback.
    event_types = {e["event_type"] for e in events}
    assert {
        "execution.started",
        "plan.ready",
        "team.ready",
        "consensus.updated",
        "execution.completed",
    } <= event_types
    assert all(e["execution_id"] == "test-exec-e2e" for e in events)
    assert any(
        "answer" in e["data"]
        for e in events
        if e["event_type"] == "execution.completed"
    )
    # Sequence numbers are dense starting at 1.
    assert [e["seq"] for e in events] == list(range(1, len(events) + 1))

    # Only mock providers were used.
    assert set(result.providers_used) <= {"mock-a", "mock-b", "mock-c"}
    assert result.providers_used != []


async def test_workspace_events_published_during_run(
    orchestrator: Orchestrator,
) -> None:
    seen: list[WorkspaceEvent] = []

    async def listener(event: WorkspaceEvent) -> None:
        seen.append(event)

    execution_id = "test-exec-workspace"
    workspace.subscribe(execution_id, listener)
    try:
        result = await orchestrator.execute(
            execution_id=execution_id,
            question="What is the mock answer?",
            time_budget_minutes=3,
        )
    finally:
        workspace.cleanup(execution_id)

    assert result.status == "completed"
    solutions = [e for e in seen if e.event_type == EventType.SOLUTION]
    assert len(solutions) >= 2
    assert {e.agent_id for e in solutions} == {"agent_01", "agent_02"}


async def test_hung_planner_falls_back_to_heuristic(
    orchestrator: Orchestrator, monkeypatch: Any
) -> None:
    """A planner call past its bound completes via heuristic (never failed).

    Regression: timeout-cancellation escaped plan()'s never-raises contract
    as an empty TimeoutError and failed the run. The orchestrator now
    substitutes the zero-call heuristic instead.
    """
    import src.orchestration.orchestrator as orch_module

    monkeypatch.setattr(orch_module, "PLANNER_CALL_SECONDS", 1)

    class _HangingPlanner(MockProvider):
        async def generate(self, messages, **kwargs):
            if self.select_script_key(messages) == "plan":
                await asyncio.sleep(5)
            return await super().generate(messages, **kwargs)

    providers = list(orchestrator.router._providers.values())
    hanging = _HangingPlanner(provider_name="mock-a")
    hanging._scripts = dict(providers[0]._scripts)
    orchestrator.router._providers["mock-a"] = hanging

    result = await orchestrator.execute(
        execution_id="test-exec-hung-planner",
        question="What is the mock answer?",
        time_budget_minutes=3,
    )
    assert result.status == "completed"
    assert result.answer != ""
    plan_calls = [c for c in hanging.calls if c.get("script_key") == "plan"]
    # At most one planner attempt: the hung call is cancelled mid-flight
    # (it may never reach the mock's call log) and never retried.
    assert len(plan_calls) <= 1
