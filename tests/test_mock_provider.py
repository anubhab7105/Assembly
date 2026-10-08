"""Unit tests for MockProvider: scripting, fixtures, faults, tokens, latency."""

import json
import time

import pytest

from src.agents.solver import SolverAgent
from src.providers.base import ChatMessage
from src.providers.mock_provider import MockProvider, MockRateLimitError


def _messages(system: str, user: str = "Test question?") -> list:
    return [ChatMessage(role="system", content=system), ChatMessage(role="user", content=user)]


async def test_scripts_selected_by_role_markers() -> None:
    provider = MockProvider()
    plan = await provider.generate(_messages("You are the Planner for Assembly."))
    solver = await provider.generate(_messages("independently analyze and solve the problem."))
    critic = await provider.generate(_messages("Your role is to find flaws in reasoning."))
    researcher = await provider.generate(_messages("research the question thoroughly and gather evidence."))
    synth = await provider.generate(_messages("You are the Final Synthesizer on a team."))

    assert json.loads(plan.content)["needs_research"] is False
    assert "42" in solver.content
    assert "supports" in critic.content
    assert "42" in researcher.content
    assert "FINAL MOCK ANSWER" in synth.content
    assert [c["script_key"] for c in provider.calls] == [
        "plan",
        "solver",
        "critic",
        "researcher",
        "synthesize",
    ]


async def test_scripts_from_dict_override() -> None:
    provider = MockProvider(scripts={"solver": {"position": "Custom!", "confidence": 1.0}})
    response = await provider.generate(_messages("independently analyze and solve."))
    assert json.loads(response.content)["position"] == "Custom!"


async def test_from_json_fixture(tmp_path) -> None:
    fixture = {
        "scripts": {"solver": {"position": "Fixture answer", "confidence": 0.5}},
        "input_tokens": 7,
        "output_tokens": 8,
    }
    path = tmp_path / "mock_fixture.json"
    path.write_text(json.dumps(fixture), encoding="utf-8")

    provider = MockProvider.from_fixture(path)
    response = await provider.generate(_messages("independently analyze and solve."))
    assert json.loads(response.content)["position"] == "Fixture answer"
    assert response.total_tokens == 15


async def test_fake_token_counts_reported() -> None:
    provider = MockProvider(input_tokens=11, output_tokens=22)
    response = await provider.generate(_messages("anything"))
    assert (response.input_tokens, response.output_tokens, response.total_tokens) == (11, 22, 33)


async def test_latency_simulated_without_network() -> None:
    provider = MockProvider(latency_seconds=0.05)
    started = time.monotonic()
    await provider.generate(_messages("anything"))
    assert time.monotonic() - started >= 0.05


async def test_rate_limit_fault_shape() -> None:
    provider = MockProvider(fail_next={"solver": "rate_limit"})
    with pytest.raises(MockRateLimitError) as exc_info:
        await provider.generate(_messages("independently analyze and solve."))
    assert exc_info.value.status_code == 429
    # fail_next pops: the retry succeeds.
    response = await provider.generate(_messages("independently analyze and solve."))
    assert "42" in response.content


async def test_timeout_fault() -> None:
    provider = MockProvider(always_fail={"solver": "timeout"})
    with pytest.raises(TimeoutError):
        await provider.generate(_messages("independently analyze and solve."))


async def test_malformed_json_triggers_text_fallback() -> None:
    provider = MockProvider(always_fail={"solver": "malformed"})
    agent = SolverAgent(agent_id="agent_01", provider=provider, model="mock-model")
    output = await agent.run("What is the answer?")
    assert output.confidence == 0.6
    assert "not JSON" in output.position


async def test_is_available_and_models() -> None:
    provider = MockProvider(provider_name="mock-x", model="mock-model-2")
    assert provider.is_available() is True
    assert provider.get_available_models() == ["mock-model-2"]
