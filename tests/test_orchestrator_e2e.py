"""End-to-end orchestrator execution using only MockProvider (zero network)."""

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
