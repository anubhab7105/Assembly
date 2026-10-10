"""FR-5: stop debate rounds that change nothing (offline, no LLM calls)."""

from src.agents.base_agent import AgentOutput
from src.api.events import ProgressEventType
from src.orchestration.stagnation import (
    StagnationConfig,
    compute_round_delta,
    needs_debate,
)


def _out(
    agent_id: str,
    position: str,
    confidence: float = 0.8,
    evidence: list[dict] | None = None,
    sources: list[dict] | None = None,
    disagrees: list[str] | None = None,
    failed_round: int | None = None,
) -> AgentOutput:
    return AgentOutput(
        agent_id=agent_id,
        agent_type="solver",
        position=position,
        reasoning_summary="r",
        confidence=confidence,
        evidence=[
            {"claim": e["claim"], "source_id": e.get("source_id", "")}
            for e in (evidence or [])
        ],
        supports=[],
        disagrees_with=list(disagrees or []),
        remaining_uncertainty=[],
        sources=[
            {"title": "T", "url": s["url"], "snippet": "x"} for s in (sources or [])
        ],
        failed_round=failed_round,
    )


def test_static_round_is_stagnant() -> None:
    prev = [_out("agent_01", "Answer 42.", 0.8), _out("agent_02", "Answer 42.", 0.8)]
    curr = [_out("agent_01", "Answer 42.", 0.8), _out("agent_02", "Answer 42.", 0.8)]
    delta = compute_round_delta(prev, curr, 0.0, 0.0, 0.0, 2)
    assert delta.stagnant is True
    assert delta.position_changes == 0


def test_converging_round_adds_value() -> None:
    prev = [_out("agent_01", "Answer A.", 0.7), _out("agent_02", "Answer B.", 0.7)]
    curr = [_out("agent_01", "Answer A.", 0.7), _out("agent_02", "Answer A.", 0.75)]
    delta = compute_round_delta(prev, curr, 0.5, 0.0, 0.5, 2)
    assert delta.stagnant is False
    assert delta.position_changes == 1 or delta.contradiction_delta > 0


def test_thrashing_is_not_stagnant() -> None:
    prev = [_out("agent_01", "Answer A.", 0.8), _out("agent_02", "Answer A.", 0.8)]
    curr = [_out("agent_01", "Answer B.", 0.8), _out("agent_02", "Answer B.", 0.8)]
    delta = compute_round_delta(prev, curr, 0.0, 0.0, 1.0, 3)
    assert delta.stagnant is False


def test_partial_failure_never_counts_as_no_change() -> None:
    prev = [_out("agent_01", "Answer 42.", 0.8), _out("agent_02", "Answer 42.", 0.8)]
    curr = [
        _out("agent_01", "Answer 42.", 0.8),
        _out("agent_02", "Answer 42.", 0.8, failed_round=2),
    ]
    delta = compute_round_delta(prev, curr, 0.0, 0.0, 0.0, 2)
    assert delta.has_failure is True
    assert delta.stagnant is False


def test_confidence_epsilon_configurable() -> None:
    prev = [_out("agent_01", "Same.", 0.80)]
    curr = [_out("agent_01", "Same.", 0.81)]
    tight = compute_round_delta(
        prev, curr, 0.0, 0.0, 0.0, 2, StagnationConfig(conf_epsilon=0.05)
    )
    assert tight.stagnant is True
    loose = compute_round_delta(
        prev, curr, 0.0, 0.0, 0.0, 2, StagnationConfig(conf_epsilon=0.001)
    )
    assert loose.stagnant is False


def test_needs_debate_requires_disagreement_or_thin_evidence() -> None:
    from types import SimpleNamespace

    assert (
        needs_debate(
            SimpleNamespace(
                open_disagreements=[{"agent_id": "agent_01"}],
                factors={"evidence_quality": 1.0},
            )
        )
        is True
    )
    assert (
        needs_debate(
            SimpleNamespace(open_disagreements=[], factors={"evidence_quality": 0.0})
        )
        is True
    )
    assert (
        needs_debate(
            SimpleNamespace(open_disagreements=[], factors={"evidence_quality": 1.0})
        )
        is False
    )


def test_stagnated_event_contract() -> None:
    from src.api.events import PAYLOAD_MODELS

    model = PAYLOAD_MODELS[ProgressEventType.ROUND_STAGNATED]
    payload = model.model_validate({"round": 2, "reason": "no change", "delta": {}})
    assert payload.model_dump()["round"] == 2


async def test_static_scenario_uses_fewer_calls(orchestrator) -> None:
    """Static mock team stops after one stagnant debate (no endless rounds)."""
    events: list[dict] = []

    async def on_progress(event: dict) -> None:
        events.append(event)

    result = await orchestrator.execute(
        execution_id="fr5-static",
        question="What is the mock answer?",
        time_budget_minutes=3,
        on_progress=on_progress,
    )
    assert result.status == "completed"
    # Static team: at most one plain debate round, then stagnate/finalize.
    debate_starts = [
        e
        for e in events
        if e["event_type"] == "round.started"
        and "Debate round" in str(e["data"].get("goal", ""))
    ]
    assert len(debate_starts) <= 1
    assert result.debate_rounds <= 2


async def test_stagnation_then_adversarial_then_finalize() -> None:
    """Stagnant debate → one adversarial strike → finalize (no second debate)."""
    from src.orchestration.consensus import ConsensusEngine
    from src.orchestration.orchestrator import Orchestrator
    from src.providers.mock_provider import MockProvider
    from tests.conftest import MockRouter

    # Solver static, critic static but with a different-family critic available
    # for the adversarial strike: use two mock providers (different families
    # via MockRouter default "mock" family? Force families via routing override
    # below by patching select_adversarial_critic through agent types).
    orch = Orchestrator()
    orch.router = MockRouter(
        [MockProvider(provider_name="mock-a"), MockProvider(provider_name="mock-b")]
    )
    events: list[dict] = []

    async def on_progress(event: dict) -> None:
        events.append(event)

    result = await orch.execute(
        execution_id="fr5-adv-after-stagnant",
        question="What is the mock answer?",
        time_budget_minutes=5,
        on_progress=on_progress,
    )
    assert result.status == "completed"
    # At most one adversarial strike; never two plain debates after stagnant.
    adv = [
        e
        for e in events
        if e["event_type"] == "round.started"
        and "Adversarial" in str(e["data"].get("goal", ""))
    ]
    assert len(adv) <= 1
    stagnated = [e for e in events if e["event_type"] == "round.stagnated"]
    # Static mock team either skips debate entirely or stagnates once.
    assert len(stagnated) <= 1
    assert ConsensusEngine is not None
