"""Per-call token measurement: input/output/reasoning propagation + call log.

All offline via MockProvider (no network). Covers step 1 of feat/tier-scaling:
providers report reasoning tokens, BaseAgent records input/output/reasoning,
debate compression preserves them, planner records provenance, and the
orchestrator builds a per-call log with stage/role/provider/model/counts.
"""

from typing import Any

from src.agents.solver import SolverAgent
from src.orchestration.orchestrator import Orchestrator
from src.providers.base import ProviderResponse
from src.providers.gemini_provider import GeminiProvider
from src.providers.mock_provider import MockProvider
from src.providers.openai_compat import OpenAICompatibleProvider


def _solver_with(provider: MockProvider) -> SolverAgent:
    return SolverAgent(
        agent_id="agent_01",
        provider=provider,
        model="mock-model",
        family="mock-fam",
    )


async def test_mock_reasoning_propagates_to_agent_output() -> None:
    provider = MockProvider(input_tokens=11, output_tokens=22, reasoning_tokens=7)
    agent = _solver_with(provider)
    output = await agent.run("What is the answer?")
    assert output.input_tokens == 11
    assert output.output_tokens == 22
    assert output.reasoning_tokens == 7
    assert output.tokens_used == 33


def test_openai_reasoning_extraction_shapes() -> None:
    extract = OpenAICompatibleProvider._extract_reasoning_tokens
    assert extract({}) == 0
    assert extract({"reasoning_tokens": 12}) == 12
    assert (
        extract({"completion_tokens_details": {"reasoning_tokens": 34}}) == 34
    )
    assert extract({"completion_tokens_details": {"reasoning": 5}}) == 5
    assert extract({"completion_tokens_details": None}) == 0


def test_gemini_reasoning_extraction() -> None:
    from types import SimpleNamespace

    extract = GeminiProvider._extract_reasoning_tokens
    assert extract(SimpleNamespace()) == 0
    assert extract(SimpleNamespace(thoughts_token_count=19)) == 19
    assert extract(SimpleNamespace(reasoning_tokens=8)) == 8


def test_debate_compression_preserves_token_split() -> None:
    from src.agents.base_agent import AgentOutput
    from src.orchestration.debate import DebateManager

    out = AgentOutput(
        agent_id="agent_01",
        agent_type="solver",
        position="x" * 10,
        reasoning_summary="y",
        confidence=0.8,
        input_tokens=100,
        output_tokens=200,
        reasoning_tokens=30,
        tokens_used=300,
    )
    compressed = DebateManager("exec-1")._compress_outputs([out])
    assert compressed[0].input_tokens == 100
    assert compressed[0].output_tokens == 200
    assert compressed[0].reasoning_tokens == 30


def test_replay_record_round_trips_reasoning() -> None:
    from src.providers.replay_provider import (
        response_from_record,
        response_to_record,
    )

    resp = ProviderResponse(
        content="hi",
        model="m",
        provider="p",
        input_tokens=5,
        output_tokens=6,
        total_tokens=11,
        reasoning_tokens=4,
    )
    record = {"response": response_to_record(resp)}
    back = response_from_record(record)
    assert back.reasoning_tokens == 4
    assert back.input_tokens == 5 and back.output_tokens == 6


async def test_orchestrator_call_log_has_stages_and_counts(
    orchestrator: Orchestrator,
) -> None:
    result = await orchestrator.execute(
        execution_id="test-exec-calllog",
        question="What is the mock answer?",
        time_budget_minutes=3,
    )
    assert result.status == "completed"
    assert result.call_log, "call log must not be empty on a completed run"
    stages = {entry["stage"] for entry in result.call_log}
    assert {"planner", "solve", "synthesis"} <= stages
    for entry in result.call_log:
        for key in (
            "stage",
            "role",
            "provider",
            "model",
            "input_tokens",
            "output_tokens",
            "reasoning_tokens",
            "total_tokens",
        ):
            assert key in entry
        # Only names and counts — never keys or prompt content.
        assert "key" not in str(entry).lower() or "mock" in str(entry).lower()


async def test_config_token_stats_have_provenance() -> None:
    from src.core.config import settings

    assert settings.token_stats_source_run_id != ""
    assert settings.token_stats_source_date != ""
    assert settings.tokens_planner_avg > 0
    assert settings.tokens_solve_avg > 0
    assert settings.tokens_debate_avg > 0
    assert settings.tokens_synthesis_avg > 0


async def test_call_log_carries_no_secrets(
    orchestrator: Orchestrator, fake_key: str, caplog: Any, monkeypatch: Any
) -> None:
    import logging

    monkeypatch.setenv("GEMINI_API_KEY", fake_key)
    with caplog.at_level(logging.INFO, logger="assembly"):
        result = await orchestrator.execute(
            execution_id="test-exec-calllog-leak",
            question="What is the mock answer?",
            time_budget_minutes=3,
        )
    assert result.status == "completed"
    assert fake_key not in caplog.text
    assert fake_key not in str(result.call_log)
