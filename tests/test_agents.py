"""Agent contract tests: strict AgentOutput, validation pipeline, calibration.

All offline via MockProvider. Failure-type coverage for BaseAgent.run():
malformed JSON, schema violations (missing/extra keys, wrong types),
out-of-range confidence (clamped, raw recorded), hallucinated agent IDs
(stripped, Fix B), retry-once semantics, family fallback via the router,
independent-solve isolation, and per-call provenance recording.
"""

import json

import pytest
from pydantic import ValidationError

from src.agents.base_agent import AgentOutput, AgentValidationError, EvidenceItem
from src.agents.critic import CriticAgent
from src.agents.researcher import ResearcherAgent
from src.agents.solver import SolverAgent
from src.agents.synthesizer import SynthesizerAgent
from src.orchestration.agent_manager import AgentManager
from src.orchestration.consensus import ConsensusEngine
from src.providers.base import ProviderResponse
from src.providers.mock_provider import MockProvider


def _valid_body(**overrides):
    body = {
        "position": "The mock answer is 42.",
        "reasoning_summary": "Mock reasoning summary.",
        "confidence": 0.9,
        "evidence": [
            {"claim": "Mock evidence point 1.", "source_id": "s1"},
            {"claim": "Mock evidence point 2.", "source_id": ""},
        ],
        "supports": [],
        "disagrees_with": [],
        "remaining_uncertainty": ["Mock caveat."],
        "sources": [
            {
                "title": "Mock Source",
                "url": "https://example.com/mock",
                "snippet": "Mock excerpt.",
            }
        ],
    }
    body.update(overrides)
    return body


def _solver_with(script=None, provider_kwargs=None):
    scripts = {"solver": script} if script is not None else None
    provider = MockProvider(scripts=scripts, **(provider_kwargs or {}))
    agent = SolverAgent(
        agent_id="agent_01", provider=provider, model="mock-model", family="mock-fam"
    )
    return agent, provider


# ── Strict schema ────────────────────────────────────────────────────


async def test_valid_output_parses_with_provenance() -> None:
    agent, provider = _solver_with(_valid_body())
    output = await agent.run("What is the answer?")

    assert isinstance(output, AgentOutput)
    assert output.position == "The mock answer is 42."
    assert output.reasoning_summary == "Mock reasoning summary."
    assert output.confidence == 0.9
    assert output.confidence_raw == 0.9
    assert [e.claim for e in output.evidence] == [
        "Mock evidence point 1.",
        "Mock evidence point 2.",
    ]
    assert output.evidence[0].source_id == "s1"
    # Per-call provenance (item 5).
    assert output.provider == "mock"
    assert output.model == "mock-model"
    assert output.family == "mock-fam"
    assert output.tokens_used == 30
    assert output.latency_ms >= 0.0
    assert output.raw_content != ""
    assert len(provider.calls) == 1


async def test_strict_model_rejects_unknown_keys() -> None:
    with pytest.raises(ValidationError):
        AgentOutput(
            agent_id="a",
            agent_type="solver",
            position="p",
            confidence=0.5,
            bogus_key="nope",
        )


async def test_evidence_item_requires_claim() -> None:
    with pytest.raises(ValidationError):
        EvidenceItem(source_id="s1")
    item = EvidenceItem(claim="c")
    assert item.source_id == ""  # source_id defaults, claim is required


# ── Failure types: malformed / schema / types ────────────────────────


async def test_malformed_json_retries_once_then_raises() -> None:
    agent, provider = _solver_with(
        _valid_body(), provider_kwargs={"always_fail": {"solver": "malformed"}}
    )
    with pytest.raises(AgentValidationError, match="no JSON object found"):
        await agent.run("What is the answer?")
    assert len(provider.calls) == 2  # initial + exactly one retry


async def test_transient_malformed_recovers_on_retry() -> None:
    agent, provider = _solver_with(
        _valid_body(), provider_kwargs={"fail_next": {"solver": "malformed"}}
    )
    output = await agent.run("What is the answer?")
    assert output.position == "The mock answer is 42."
    assert len(provider.calls) == 2


async def test_missing_required_field_retries_then_raises() -> None:
    body = _valid_body()
    del body["position"]
    agent, provider = _solver_with(body)
    with pytest.raises(AgentValidationError):
        await agent.run("What is the answer?")
    assert len(provider.calls) == 2


async def test_empty_position_rejected() -> None:
    agent, provider = _solver_with(_valid_body(position=""))
    with pytest.raises(AgentValidationError):
        await agent.run("What is the answer?")
    assert len(provider.calls) == 2


async def test_non_numeric_confidence_rejected() -> None:
    agent, _ = _solver_with(_valid_body(confidence="very sure"))
    with pytest.raises(AgentValidationError, match="confidence must be a number"):
        await agent.run("What is the answer?")


async def test_boolean_confidence_rejected() -> None:
    agent, _ = _solver_with(_valid_body(confidence=True))
    with pytest.raises(AgentValidationError, match="confidence must be a number"):
        await agent.run("What is the answer?")


async def test_evidence_strings_rejected_as_not_objects() -> None:
    agent, _ = _solver_with(_valid_body(evidence=["just a string"]))
    with pytest.raises(AgentValidationError):
        await agent.run("What is the answer?")


async def test_unknown_top_level_key_rejected() -> None:
    agent, _ = _solver_with(_valid_body(reasoning="legacy long-form reasoning"))
    with pytest.raises(AgentValidationError):
        await agent.run("What is the answer?")


async def test_retry_appends_validation_error() -> None:
    """The retry prompt carries the error so the model can repair its reply."""
    seen_messages: list = []

    class RecordingProvider(MockProvider):
        async def generate(self, messages, **kwargs):
            seen_messages.append([m.content for m in messages])
            if len(seen_messages) == 1:
                return ProviderResponse(
                    content="not json at all",
                    model="m",
                    provider="mock",
                    total_tokens=1,
                )
            return await super().generate(messages, **kwargs)

    provider = RecordingProvider()
    agent = SolverAgent(agent_id="agent_01", provider=provider, model="mock-model")
    output = await agent.run("What is the answer?")
    assert output.position == "The mock answer is 42."
    assert len(seen_messages) == 2
    assert len(seen_messages[1]) == 3  # system + user + error note
    assert "invalid" in seen_messages[1][2]


# ── Calibration (item 4) ─────────────────────────────────────────────


async def test_out_of_range_confidence_clamped_with_raw_recorded() -> None:
    agent, _ = _solver_with(_valid_body(confidence=1.5))
    output = await agent.run("What is the answer?")
    assert output.confidence == 1.0
    assert output.confidence_raw == 1.5
    assert output.calibrated_confidence == 1.0


async def test_negative_confidence_clamped_to_zero() -> None:
    agent, _ = _solver_with(_valid_body(confidence=-0.3))
    output = await agent.run("What is the answer?")
    assert output.confidence == 0.0
    assert output.confidence_raw == -0.3


def test_calibrate_rejects_non_finite_and_non_numbers() -> None:
    assert AgentOutput.calibrate_confidence(0.7) == (0.7, 0.7)
    assert AgentOutput.calibrate_confidence(2) == (1.0, 2.0)
    for bad in (float("nan"), float("inf"), float("-inf")):
        with pytest.raises(ValueError):
            AgentOutput.calibrate_confidence(bad)
    for bad in ("high", None, True):
        with pytest.raises(TypeError):
            AgentOutput.calibrate_confidence(bad)


async def test_long_reasoning_summary_truncated_not_rejected() -> None:
    agent, _ = _solver_with(_valid_body(reasoning_summary="x" * 5000))
    output = await agent.run("What is the answer?")
    assert len(output.reasoning_summary) <= 2000 + len("... [truncated]")
    assert output.reasoning_summary.endswith("... [truncated]")


async def test_consensus_uses_calibrated_values() -> None:
    high, _ = _solver_with(_valid_body(confidence=1.5))
    low, _ = _solver_with(_valid_body(confidence=-0.5))
    out_high = await high.run("Q?")
    out_low = await low.run("Q?")
    result = ConsensusEngine().evaluate([out_high, out_low], round_number=1)
    assert result.average_confidence == pytest.approx(0.5)  # (1.0 + 0.0) / 2


# ── Agent-ID validation (Fix B) ──────────────────────────────────────


async def test_hallucinated_agent_ids_stripped_in_critique() -> None:
    body = _valid_body(supports=["agent_01", "agent_99"], disagrees_with=["ghost"])
    provider = MockProvider(scripts={"critic": body})
    agent = CriticAgent(agent_id="agent_02", provider=provider, model="mock-model")
    others = [
        AgentOutput(
            agent_id="agent_01",
            agent_type="solver",
            position="Other position.",
            confidence=0.8,
        )
    ]
    output = await agent.critique("What is the answer?", others, round_number=2)
    assert output.supports == ["agent_01"]
    assert output.disagrees_with == []


async def test_valid_ids_pass_through() -> None:
    body = _valid_body(supports=["agent_01"], disagrees_with=["agent_03"])
    provider = MockProvider(scripts={"critic": body})
    agent = CriticAgent(agent_id="agent_02", provider=provider, model="mock-model")
    others = [
        AgentOutput(
            agent_id="agent_01",
            agent_type="solver",
            position="P1.",
            confidence=0.8,
        ),
        AgentOutput(
            agent_id="agent_03",
            agent_type="researcher",
            position="P3.",
            confidence=0.7,
        ),
    ]
    output = await agent.critique("Q?", others, round_number=1)
    assert output.supports == ["agent_01"]
    assert output.disagrees_with == ["agent_03"]


# ── Family fallback via the router (item 2) ──────────────────────────


class _StubDecision:
    def __init__(self, provider, model, name, family, role="solver"):
        self.provider = provider
        self.model = model
        self.provider_name = name
        self.family = family
        self.role = role
        self.reason = "stub"


class _StubRouter:
    def __init__(self, fallback):
        self._fallback = fallback

    def fallback_for(self, decision, error):
        assert isinstance(error, AgentValidationError)
        return self._fallback


async def test_fallback_to_another_family_recovers() -> None:
    primary = MockProvider(always_fail={"solver": "malformed"}, provider_name="mock-a")
    alt = MockProvider(provider_name="mock-b", model="mock-model-b")
    decision = _StubDecision(primary, "mock-model", "mock-a", "fam-a")
    fallback = _StubDecision(alt, "mock-model-b", "mock-b", "fam-b")
    agent = SolverAgent(
        agent_id="agent_01",
        provider=primary,
        model="mock-model",
        router=_StubRouter(fallback),
        routing=decision,
        family="fam-a",
    )
    output = await agent.run("What is the answer?")
    assert output.position == "The mock answer is 42."
    assert output.family == "fam-b"
    assert output.provider == "mock-b"
    assert len(primary.calls) == 2  # initial + retry on the primary
    assert len(alt.calls) == 1  # then one fallback-family attempt


async def test_failed_fallback_raises_for_manager() -> None:
    primary = MockProvider(always_fail={"solver": "malformed"}, provider_name="mock-a")
    alt = MockProvider(always_fail={"solver": "malformed"}, provider_name="mock-b")
    decision = _StubDecision(primary, "mock-model", "mock-a", "fam-a")
    fallback = _StubDecision(alt, "mock-model-b", "mock-b", "fam-b")
    agent = SolverAgent(
        agent_id="agent_01",
        provider=primary,
        model="mock-model",
        router=_StubRouter(fallback),
        routing=decision,
        family="fam-a",
    )
    with pytest.raises(AgentValidationError):
        await agent.run("What is the answer?")


async def test_manager_converts_failure_to_error_output(mock_router) -> None:
    provider = MockProvider(always_fail={"solver": "malformed"})
    manager = AgentManager(mock_router, "exec-fail")
    agent = SolverAgent(agent_id="agent_01", provider=provider, model="mock-model")
    manager.agents["agent_01"] = agent
    outputs = await manager.run_all_independent([agent], "What is the answer?")
    assert len(outputs) == 1
    assert outputs[0].confidence == 0.1
    assert "Unable to complete analysis" in outputs[0].position


# ── Independent-solve isolation (item 3) ─────────────────────────────


def _other_position_text(agent, question, other_id, other_position) -> str:
    prompt = agent.build_user_prompt(question)
    assert other_id not in prompt
    assert other_position not in prompt
    return prompt


async def test_independent_prompts_exclude_other_agents() -> None:
    question = "What is the mock answer?"
    other_id = "agent_99"
    other_position = "Rival position that must stay invisible."
    for agent in (
        SolverAgent(agent_id="a1", provider=MockProvider(), model="m"),
        ResearcherAgent(agent_id="a2", provider=MockProvider(), model="m"),
        CriticAgent(agent_id="a3", provider=MockProvider(), model="m"),
    ):
        _other_position_text(agent, question, other_id, other_position)


async def test_independent_run_sends_no_other_answers() -> None:
    seen: list = []

    class SniffingProvider(MockProvider):
        async def generate(self, messages, **kwargs):
            seen.append("\n".join(m.content for m in messages))
            return await super().generate(messages, **kwargs)

    agent = SolverAgent(agent_id="a1", provider=SniffingProvider(), model="m")
    await agent.run("What is the standalone question?")
    assert len(seen) == 1
    assert "agent_99" not in seen[0]
    assert "Rival position" not in seen[0]


async def test_researcher_still_sees_search_results() -> None:
    """Web results are data, not agents' answers — the researcher keeps them."""
    agent = ResearcherAgent(agent_id="a2", provider=MockProvider(), model="m")
    agent.search_results = [
        {"title": "T", "url": "https://example.com/t", "snippet": "S"}
    ]
    prompt = agent.build_user_prompt("Q?")
    assert "https://example.com/t" in prompt


# ── Synthesizer ──────────────────────────────────────────────────────


async def test_synthesizer_collects_sources_and_footer() -> None:
    agent = SynthesizerAgent(agent_id="agent_09", provider=MockProvider(), model="m")
    team = [
        AgentOutput(
            agent_id="agent_01",
            agent_type="solver",
            position="P1.",
            confidence=0.8,
            sources=[
                {
                    "title": "S",
                    "url": "https://example.com/s",
                    "snippet": "x",
                }
            ],
        )
    ]
    result = await agent.synthesize(
        question="Q?",
        agent_outputs=team,
        consensus_score=0.9,
        debate_rounds=1,
        providers_used=["groq"],
    )
    assert "FINAL MOCK ANSWER" in result.position
    assert "assembled by 1 AI agents" in result.position
    assert result.tokens_used == 30


# ── Key-leak scan (AGENTS.md section 5) ──────────────────────────────


async def test_fake_key_absent_from_output_and_logs(fake_key, caplog) -> None:
    import logging

    agent, _ = _solver_with(_valid_body())
    with caplog.at_level(logging.INFO, logger="assembly"):
        output = await agent.run(f"What is the answer? {fake_key}")
    assert fake_key not in json.dumps(output.to_dict())
    assert fake_key not in caplog.text
