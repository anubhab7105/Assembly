"""Circuit breaker + tool-call failover tests (all offline, MockProvider).

Covers the Groq gpt-oss fix end to end:
- ToolCallError taxonomy (a BadResponse, so old handlers still catch it)
  and detection (400 tool_use_failed bodies; 200s with tool_calls and no
  content).
- MockProvider "tool_call" fault injection.
- CircuitBreaker unit semantics (trip at 2, per-instance isolation).
- AgentManager retry records failures, skips open models when picking a
  fallback, and reroutes open-circuited agents mid-run (same agent_id).
- Orchestrator run where the researcher always fails: breaker trips emit
  visible agent.status events and the answer reports reduced research
  (verification flag + warning + uncertainty caveat).
"""

import pytest

from src.agents.base_agent import AgentOutput
from src.orchestration.agent_manager import AgentManager
from src.orchestration.circuit_breaker import CircuitBreaker
from src.orchestration.composer import compose_final_answer
from src.orchestration.orchestrator import Orchestrator, _research_degraded
from src.providers.base import ChatMessage
from src.providers.errors import BadResponse, ToolCallError
from src.providers.gemini_provider import GeminiProvider
from src.providers.mock_provider import MockProvider
from src.providers.openai_compat import (
    OpenAICompatibleProvider,
    _tool_use_failure_message,
)

# ── Breaker unit ────────────────────────────────────────────────────


def test_breaker_trips_on_second_failure() -> None:
    breaker = CircuitBreaker()
    assert breaker.record_failure("m", "researcher") is False
    assert breaker.is_open("m", "researcher") is False
    assert breaker.record_failure("m", "researcher") is True
    assert breaker.is_open("m", "researcher") is True
    assert breaker.failure_count("m", "researcher") == 2


def test_breaker_is_per_role_and_per_instance() -> None:
    breaker = CircuitBreaker()
    breaker.record_failure("m", "researcher")
    breaker.record_failure("m", "researcher")
    assert breaker.is_open("m", "solver") is False
    assert breaker.is_open("other", "researcher") is False
    assert breaker.failures_for_role("researcher") == 2
    assert breaker.failures_for_role("solver") == 0
    fresh = CircuitBreaker()
    assert fresh.is_open("m", "researcher") is False
    assert [t["model"] for t in breaker.trips] == ["m"]


# ── Cross-run health memory ─────────────────────────────────────────


@pytest.fixture(autouse=True)
def _fresh_cross_run_memory():
    from src.orchestration import circuit_breaker as breaker_module

    breaker_module.reset_cross_run_health()
    yield
    breaker_module.reset_cross_run_health()


def test_cross_run_memory_avoids_after_two_failures() -> None:
    from src.orchestration.circuit_breaker import (
        CROSS_RUN_TTL_SECONDS,
        CrossRunHealth,
        cross_run_health,
    )

    assert CROSS_RUN_TTL_SECONDS == 1800.0
    memory = CrossRunHealth()
    assert memory.is_avoided("m", "researcher") is False
    assert memory.record_failure("m", "researcher") is False
    assert memory.record_failure("m", "researcher") is True
    assert memory.is_avoided("m", "researcher") is True
    assert memory.is_avoided("m", "solver") is False
    assert cross_run_health().is_avoided("m", "researcher") is False


def test_cross_run_memory_expires_after_ttl() -> None:
    from src.orchestration.circuit_breaker import CrossRunHealth

    memory = CrossRunHealth(ttl_seconds=0.0)
    memory.record_failure("m", "researcher")
    memory.record_failure("m", "researcher")
    assert memory.is_avoided("m", "researcher") is False


async def test_manager_skips_cross_run_avoided_model_with_log(caplog) -> None:
    import logging

    from src.agents.researcher import ResearcherAgent
    from src.orchestration.circuit_breaker import cross_run_health

    flaky = MockProvider(
        always_fail={"researcher": "tool_call"}, provider_name="mock-a"
    )
    avoided = MockProvider(provider_name="mock-b", model="mock-model-b")
    healthy = MockProvider(provider_name="mock-c", model="mock-model-c")
    router = _ChainRouter(
        [
            _StubDecision(avoided, "mock-model-b", "mock-b", "fam-b"),
            _StubDecision(healthy, "mock-model-c", "mock-c", "fam-c"),
        ]
    )
    manager = AgentManager(router, "exec-xrun")
    agent = ResearcherAgent(
        agent_id="agent_02", provider=flaky, model="mock-model", family="fam-a"
    )
    manager.agents["agent_02"] = agent
    manager._decisions["agent_02"] = _StubDecision(
        flaky, "mock-model", "mock-a", "fam-a"
    )
    cross_run_health().record_failure("mock-model-b", "researcher")
    cross_run_health().record_failure("mock-model-b", "researcher")
    with caplog.at_level(logging.WARNING, logger="assembly"):
        output = await manager._run_with_retry(agent, "Q?")
    assert output.provider == "mock-c"
    assert "Skipping mock-model-b for researcher" in caplog.text
    assert "cross-run" in caplog.text


# ── ToolCallError taxonomy + detection ──────────────────────────────


def test_tool_call_error_is_a_bad_response() -> None:
    err = ToolCallError("groq", "Tool choice is none, but model called a tool")
    assert isinstance(err, BadResponse)
    assert err.provider == "groq"


def test_tool_use_failure_message_detects_groq_400() -> None:
    body = {
        "error": {
            "message": "Tool choice is none, but model called a tool",
            "type": "invalid_request_error",
            "code": "tool_use_failed",
        }
    }
    assert (
        _tool_use_failure_message(400, body, "fallback")
        == "Tool choice is none, but model called a tool"
    )
    assert _tool_use_failure_message(429, body, "fallback") is None
    assert _tool_use_failure_message(400, {"error": "plain"}, "fb") is None
    assert _tool_use_failure_message(400, None, "fb") is None


def _compat_provider() -> OpenAICompatibleProvider:
    return OpenAICompatibleProvider(
        provider_id="probe",
        api_key="test-key",
        base_url="http://localhost:1",
        default_model="m",
    )


def test_to_response_raises_on_tool_calls_without_content() -> None:
    provider = _compat_provider()
    data = {
        "choices": [
            {
                "message": {
                    "role": "assistant",
                    "content": "",
                    "tool_calls": [
                        {"function": {"name": "browser.search", "arguments": "{}"}}
                    ],
                },
                "finish_reason": "tool_calls",
            }
        ],
        "usage": {},
    }
    with pytest.raises(ToolCallError, match="browser.search"):
        provider._to_response(data, "m")


def test_to_response_prefers_content_over_tool_calls() -> None:
    provider = _compat_provider()
    data = {
        "choices": [
            {
                "message": {
                    "role": "assistant",
                    "content": "hello",
                    "tool_calls": [{"function": {"name": "x"}}],
                },
                "finish_reason": "stop",
            }
        ],
        "usage": {"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2},
    }
    response = provider._to_response(data, "m")
    assert response.content == "hello"


async def test_mock_tool_call_fault() -> None:
    provider = MockProvider(always_fail={"solver": "tool_call"})
    with pytest.raises(ToolCallError, match="Tool choice is none"):
        await provider.generate(
            [ChatMessage(role="system", content="independently analyze and solve")]
        )


# ── Manager retry + skip-open + reroute ─────────────────────────────


class _StubDecision:
    def __init__(self, provider, model, name, family, role="researcher"):
        self.provider = provider
        self.model = model
        self.provider_name = name
        self.family = family
        self.role = role
        self.reason = "stub"


class _ChainRouter:
    """fallback_for walks a fixed chain of decisions."""

    def __init__(self, chain):
        self._chain = list(chain)

    def fallback_for(self, decision, error):
        for candidate in self._chain:
            if (candidate.provider_name, candidate.model) != (
                decision.provider_name,
                decision.model,
            ):
                return candidate
        return None


def _researcher_agent(provider, name="mock-a", model="mock-model", family="fam-a"):
    from src.agents.researcher import ResearcherAgent

    return ResearcherAgent(
        agent_id="agent_02", provider=provider, model=model, family=family
    )


async def test_manager_retries_tool_call_on_fallback() -> None:
    from tests.conftest import MockRouter

    bad = MockProvider(always_fail={"researcher": "tool_call"}, provider_name="mock-a")
    good = MockProvider(provider_name="mock-b", model="mock-model-b")
    router = MockRouter([bad, good])
    manager = AgentManager(router, "exec-tool")
    agent = _researcher_agent(bad)
    decision = _StubDecision(bad, "mock-model", "mock-a", "fam-a")
    manager.agents["agent_02"] = agent
    manager._decisions["agent_02"] = decision
    # No fallback_for on the shared MockRouter: failure must propagate
    # to the low-confidence error output (fail-open, run survives).
    outputs = await manager.run_all_independent([agent], "Q?")
    assert outputs[0].confidence == 0.1
    assert manager.breaker.failure_count("mock-model", "researcher") == 1


async def test_manager_skips_open_model_in_fallback() -> None:
    from src.agents.researcher import ResearcherAgent

    flaky = MockProvider(
        always_fail={"researcher": "tool_call"}, provider_name="mock-a"
    )
    also_bad = MockProvider(provider_name="mock-b", model="mock-model-b")
    healthy = MockProvider(provider_name="mock-c", model="mock-model-c")
    d_bad = _StubDecision(also_bad, "mock-model-b", "mock-b", "fam-b")
    d_good = _StubDecision(healthy, "mock-model-c", "mock-c", "fam-c")
    router = _ChainRouter([d_bad, d_good])

    manager = AgentManager(router, "exec-skip")
    agent = ResearcherAgent(
        agent_id="agent_02", provider=flaky, model="mock-model", family="fam-a"
    )
    manager.agents["agent_02"] = agent
    manager._decisions["agent_02"] = _StubDecision(
        flaky, "mock-model", "mock-a", "fam-a"
    )
    # Pre-trip mock-model-b for researcher: the retry must land on mock-c.
    manager.breaker.record_failure("mock-model-b", "researcher")
    manager.breaker.record_failure("mock-model-b", "researcher")
    output = await manager._run_with_retry(agent, "Q?")
    assert output.provider == "mock-c"
    assert output.model == "mock-model-c"


async def test_reroute_open_circuit_swaps_model_same_id() -> None:
    agent = _researcher_agent(
        MockProvider(provider_name="mock-a"), model="mock-model", family="fam-a"
    )
    good = MockProvider(provider_name="mock-b", model="mock-model-b")
    router = _ChainRouter([_StubDecision(good, "mock-model-b", "mock-b", "fam-b")])
    manager = AgentManager(router, "exec-reroute")
    manager.agents["agent_02"] = agent
    manager._decisions["agent_02"] = _StubDecision(
        agent.provider, "mock-model", "mock-a", "fam-a"
    )
    manager.breaker.record_failure("mock-model", "researcher")
    manager.breaker.record_failure("mock-model", "researcher")
    label = manager.reroute_open_circuit(agent)
    assert label == "mock-b/mock-model-b"
    assert manager.agents["agent_02"].model == "mock-model-b"
    assert manager.agents["agent_02"].agent_id == "agent_02"


async def test_reroute_without_fallback_returns_none() -> None:
    from tests.conftest import MockRouter

    agent = _researcher_agent(MockProvider(provider_name="mock-a"))
    manager = AgentManager(MockRouter([agent.provider]), "exec-noroute")
    manager.agents["agent_02"] = agent
    assert manager.reroute_open_circuit(agent) is None


# ── Gemini reasoning extractor ──────────────────────────────────────


def test_gemini_extractor_reads_camel_case_and_dicts() -> None:
    from types import SimpleNamespace

    extract = GeminiProvider._extract_reasoning_tokens
    assert extract(SimpleNamespace(thoughtsTokenCount=44)) == 44
    assert extract({"thoughtsTokenCount": 12}) == 12
    assert extract({"reasoningTokens": 7}) == 7
    assert extract(SimpleNamespace(thoughts_token_count=19)) == 19
    assert extract({}) == 0
    assert extract(SimpleNamespace()) == 0


async def test_est_tokens_include_reasoning_reserve(monkeypatch) -> None:
    from src.core.config import settings

    seen: dict[str, int] = {}

    class _Lease:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            return False

    class _Limiter:
        def __init__(self) -> None:
            self.acquires = 0

        async def acquire(self, provider, key_id, model_name="", est_tokens=0):
            self.acquires += 1
            seen["est"] = est_tokens
            seen["model"] = model_name
            return _Lease()

        def report_429(self, *args, **kwargs):
            pass

    limiter = _Limiter()
    monkeypatch.setattr("src.providers.quota.get_limiter", lambda **kwargs: limiter)

    async def _fake_post(self, payload):
        return {
            "choices": [{"message": {"content": "hi"}, "finish_reason": "stop"}],
            "usage": {
                "prompt_tokens": 1,
                "completion_tokens": 1,
                "total_tokens": 2,
            },
        }

    monkeypatch.setattr(OpenAICompatibleProvider, "_post_with_retry", _fake_post)
    provider = _compat_provider()
    await provider.generate(
        [ChatMessage(role="user", content="hi")], model="m", max_tokens=100
    )
    assert seen["est"] == 100 + settings.tokens_reasoning_reserve
    assert seen["model"] == "m"
    assert limiter.acquires == 1, "exactly one quota lease per generate()"


async def test_gemini_acquires_exactly_one_lease(monkeypatch) -> None:
    """Gemini generate() takes exactly one quota lease (single-lease rule).

    The per-model rebase split generate()/_generate_inner must not
    introduce a second acquire; the lease carries model_name for the
    per-(provider, model) limiter plus the reasoning reserve.
    """
    from src.core.config import settings
    from src.providers.gemini_provider import GeminiProvider

    seen: dict[str, object] = {}

    class _Lease:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            return False

    class _Limiter:
        def __init__(self) -> None:
            self.acquires = 0

        async def acquire(self, provider, key_id, model_name="", est_tokens=0):
            self.acquires += 1
            seen["est"] = est_tokens
            seen["model"] = model_name
            return _Lease()

        def report_429(self, *args, **kwargs):
            pass

    limiter = _Limiter()
    monkeypatch.setattr("src.providers.quota.get_limiter", lambda **kwargs: limiter)

    async def _fake_inner(self, messages, model_name, temperature, max_tokens):
        from types import SimpleNamespace

        return SimpleNamespace(text="{}", usage_metadata=None)

    monkeypatch.setattr(GeminiProvider, "_generate_inner", _fake_inner)
    provider = GeminiProvider(api_key="test-key", default_model="m")
    await provider.generate(
        [ChatMessage(role="user", content="hi")], model="m", max_tokens=100
    )
    assert seen["est"] == 100 + settings.tokens_reasoning_reserve
    assert seen["model"] == "m"
    assert limiter.acquires == 1, "exactly one quota lease per generate()"


# ── Research-health helper + degraded answer ────────────────────────


def _output(
    agent_id: str,
    position: str,
    confidence: float,
    agent_type: str = "solver",
    family: str = "fam",
) -> AgentOutput:
    return AgentOutput(
        agent_id=agent_id,
        agent_type=agent_type,
        position=position,
        reasoning_summary="r",
        confidence=confidence,
        provider="mock",
        model="mock-model",
        family=family,
    )


def test_research_degraded_helper() -> None:
    from types import SimpleNamespace

    agents = [
        SimpleNamespace(agent_type="solver"),
        SimpleNamespace(agent_type="researcher"),
    ]
    assert _research_degraded(agents, []) is True
    assert (
        _research_degraded(
            agents,
            [{"role": "researcher", "stage": "solve", "total_tokens": 10}],
        )
        is False
    )
    assert (
        _research_degraded(
            agents,
            [{"role": "researcher", "stage": "solve", "total_tokens": 0}],
        )
        is True
    )
    assert _research_degraded([SimpleNamespace(agent_type="solver")], []) is False


def test_degraded_research_reported_even_at_high_band() -> None:
    team = [_output("agent_01", "P.", 0.95), _output("agent_02", "P.", 0.93)]
    composed = compose_final_answer(
        agent_outputs=team,
        consensus_score=0.9,
        open_disagreements=[],
        sources_pool=[],
        debate_rounds=1,
        synth_position="P.",
        research_degraded=True,
        research_failures=3,
        circuit_breaker_trips=["mock-model on researcher"],
    )
    assert composed.verification.research_degraded is True
    assert composed.verification.research_failures == 3
    assert composed.verification.circuit_breaker_trips == ("mock-model on researcher",)
    assert "research" in composed.uncertainty_note.casefold()
    assert "research" in composed.answer_markdown.casefold()
    assert any("Research degraded" in w for w in composed.warnings)


# ── Full run where the researcher always fails ──────────────────────


def _plan_with_researcher() -> dict:
    return {
        "problem_type": "general",
        "complexity": "medium",
        "needs_research": False,
        "team": [
            {"agent_type": "solver", "role_description": "Problem solver"},
            {"agent_type": "researcher", "role_description": "Evidence gatherer"},
            {"agent_type": "critic", "role_description": "Answer verifier"},
        ],
        "reasoning": "Chaos plan with researcher.",
    }


async def test_run_with_failing_researcher_reports_reduced_research() -> None:
    from tests.conftest import MockRouter

    providers = [
        MockProvider(provider_name="mock-a", always_fail={"researcher": "rate_limit"}),
        MockProvider(provider_name="mock-b"),
        MockProvider(provider_name="mock-c"),
    ]
    scripts = dict(MockProvider()._scripts)
    scripts["plan"] = _plan_with_researcher()
    for provider in providers:
        provider._scripts = dict(scripts)
    router = MockRouter(providers)
    orch = Orchestrator()
    orch.router = router

    events: list[dict] = []

    async def on_progress(event: dict) -> None:
        events.append(event)

    result = await orch.execute(
        execution_id="test-exec-bad-researcher",
        question="What is the mock answer?",
        time_budget_minutes=3,
        on_progress=on_progress,
    )
    assert result.status == "completed"
    assert result.verification.get("research_degraded") is True
    assert result.verification.get("research_failures", 0) >= 1
    assert any("Research degraded" in w for w in result.warnings)
    assert "research" in result.answer.casefold()
    trips = [
        e
        for e in events
        if e.get("event_type") == "agent.status"
        and "Circuit breaker" in str(e.get("data", {}).get("activity", ""))
    ]
    assert trips, "breaker trip must surface as a visible agent.status event"
    assert result.verification.get("circuit_breaker_trips"), (
        "trips must appear in the verification summary"
    )


async def test_call_log_schema_carries_names_and_counts_only(
    fake_key: str,
) -> None:
    """Call-log entries hold exactly the documented schema: stage, role,
    provider/model/family names, and token counts. No prompt content,
    no keys — structurally, there is no field where either could hide."""
    from tests.conftest import MockRouter

    providers = [MockProvider(provider_name="mock-a")]
    router = MockRouter(providers)
    orch = Orchestrator()
    orch.router = router
    result = await orch.execute(
        execution_id="test-exec-calllog-schema",
        question=f"What is the mock answer? {fake_key}",
        time_budget_minutes=3,
    )
    assert result.status == "completed"
    assert result.call_log
    allowed = {
        "stage",
        "round",
        "role",
        "agent_id",
        "provider",
        "model",
        "family",
        "input_tokens",
        "output_tokens",
        "reasoning_tokens",
        "total_tokens",
    }
    blob = ""
    for entry in result.call_log:
        assert set(entry) == allowed, set(entry)
        blob += str(entry)
    assert fake_key not in blob
