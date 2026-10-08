"""End-to-end orchestrator execution using only MockProvider (zero network)."""

from typing import Any, Dict, List

from src.orchestration.orchestrator import Orchestrator
from src.orchestration.workspace import EventType, WorkspaceEvent, workspace
from src.providers.mock_provider import MockProvider


async def test_full_execution_end_to_end(orchestrator: Orchestrator) -> None:
    events: List[Dict[str, Any]] = []

    async def on_progress(event: Dict[str, Any]) -> None:
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

    # Tokens are tracked: every non-planner mock call reports 30 tokens.
    providers: List[MockProvider] = list(orchestrator.router._providers.values())
    total_calls = sum(len(p.calls) for p in providers)
    plan_calls = sum(1 for p in providers for c in p.calls if c["script_key"] == "plan")
    assert total_calls > 0
    assert result.total_tokens == (total_calls - plan_calls) * 30

    # Events are published to the progress callback.
    event_types = {e["event_type"] for e in events}
    assert {"status_update", "agent_update", "consensus_update", "answer_ready"} <= event_types
    assert all(e["execution_id"] == "test-exec-e2e" for e in events)
    assert any("answer" in e["data"] for e in events if e["event_type"] == "answer_ready")

    # Only mock providers were used.
    assert set(result.providers_used) <= {"mock-a", "mock-b", "mock-c"}
    assert result.providers_used != []


async def test_workspace_events_published_during_run(orchestrator: Orchestrator) -> None:
    seen: List[WorkspaceEvent] = []

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
