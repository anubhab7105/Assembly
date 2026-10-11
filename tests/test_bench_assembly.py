"""Offline tests for bench/run_assembly.py --pin-team helpers (no network)."""

from types import SimpleNamespace

import pytest

from bench.run_assembly import (
    PIN_MAX_WAIT_CAP_SECONDS,
    PIN_REQUIRED_ROLES,
    _answered_families,
    _check_pin_wait,
    _cooling_providers,
    _has_quota_signal,
    _pin_role_coverage,
    _pin_wait_line,
    _quota_wait_seconds,
    _routed_families,
    parse_args,
    validate_pins,
)


def test_parse_args_pin_team_defaults() -> None:
    args = parse_args([])
    assert args.pin_team is False
    assert args.pin_families is None


def test_parse_args_pin_team_flags() -> None:
    args = parse_args(["--pin-team", "--pin-families", "gemini,qwen", "--tier", "5"])
    assert args.pin_team is True
    assert args.pin_families == "gemini,qwen"


def test_answered_families_prefers_successful_calls() -> None:
    result = SimpleNamespace(
        call_log=[
            {"family": "gemini", "total_tokens": 100},
            {"family": "nemotron", "total_tokens": 200},
            {"family": "gpt-oss", "total_tokens": 0},
            {"family": "unknown", "total_tokens": 50},
            {"family": "", "total_tokens": 10},
        ],
        routing=[{"family": "gemini"}, {"family": "gpt-oss"}],
    )
    assert _answered_families(result) == ["gemini", "nemotron"]
    assert _routed_families(result) == ["gemini", "gpt-oss"]


def test_answered_families_falls_back_to_routing() -> None:
    result = SimpleNamespace(call_log=[], routing=[{"family": "qwen"}])
    assert _answered_families(result) == ["qwen"]


def test_has_quota_signal() -> None:
    assert _has_quota_signal([{"type": "RateLimited", "message": "x"}]) is True
    assert _has_quota_signal([{"type": "Warning", "message": "quota spent"}]) is True
    assert _has_quota_signal([{"type": "Warning", "message": "all good"}]) is False
    assert _has_quota_signal([]) is False


def test_quota_wait_seconds() -> None:
    router = SimpleNamespace(
        quota_snapshot=lambda: [
            {"provider": "a", "cooldown_seconds": 12.0},
            {"provider": "b", "cooldown_seconds": 0.0},
        ]
    )
    assert _quota_wait_seconds(router) == 12.0
    assert _quota_wait_seconds(SimpleNamespace()) == 0.0


def test_pin_wait_cap_accepts_up_to_24h() -> None:
    assert _check_pin_wait(1.0) == 1.0
    assert _check_pin_wait(86400.0) == 86400.0
    assert PIN_MAX_WAIT_CAP_SECONDS == 86400.0
    with pytest.raises(SystemExit):
        _check_pin_wait(0.0)
    with pytest.raises(SystemExit):
        _check_pin_wait(-5.0)
    with pytest.raises(SystemExit):
        _check_pin_wait(86400.0 + 1)


def test_cooling_providers_names_who_is_cooling() -> None:
    router = SimpleNamespace(
        quota_snapshot=lambda: [
            {"provider": "groq", "cooldown_seconds": 90.0},
            {"provider": "gemini", "cooldown_seconds": 0.0},
        ]
    )
    assert _cooling_providers(router) == ["groq"]
    assert _cooling_providers(SimpleNamespace()) == []


def test_pin_wait_line_names_provider_and_time() -> None:
    line = _pin_wait_line(["groq"], 90.0)
    assert line.startswith("waiting for groq quota until ")
    multi = _pin_wait_line(["groq", "openrouter"], 60.0)
    assert multi.startswith("waiting for groq, openrouter quota until ")
    assert "T" in line  # ISO-8601 timestamp trails the provider names


# ── Pin validation + enforcement threading ──────────────────────────


def _stub_router(coverage: dict) -> SimpleNamespace:
    """Router double exposing config catalog + live providers (no network)."""

    def _model(family: str, roles: list) -> SimpleNamespace:
        return SimpleNamespace(id=f"{family}-m", family=family, roles=list(roles))

    providers = {}
    for pid, fams in coverage.items():
        providers[pid] = SimpleNamespace(
            models=[_model(fam, roles) for fam, roles in fams]
        )
    return SimpleNamespace(
        get_available_providers=lambda: sorted(providers),
        config=SimpleNamespace(providers=providers),
    )


def _full_coverage() -> dict:
    return {
        "pa": [("gpt-oss", ["solver", "critic", "planner", "synthesizer"])],
        "pb": [("qwen", ["solver", "researcher"])],
        "pc": [("nemotron", ["solver", "critic", "synthesizer"])],
    }


def test_validate_pins_accepts_feasible_set(capsys) -> None:
    validate_pins(_stub_router(_full_coverage()), ["gpt-oss", "qwen", "nemotron"])
    assert "Pins feasible" in capsys.readouterr().out


def test_validate_pins_aborts_on_critic_gap() -> None:
    coverage = {
        "pa": [("gpt-oss", ["solver", "planner", "synthesizer"])],
        "pb": [("qwen", ["solver", "researcher"])],
    }
    with pytest.raises(SystemExit, match="critic"):
        validate_pins(_stub_router(coverage), ["gpt-oss", "qwen"])


def test_validate_pins_warns_only_on_researcher_gap(capsys) -> None:
    coverage = {
        "pa": [("gpt-oss", ["solver", "critic", "planner", "synthesizer"])],
    }
    # No researcher anywhere live: warning, not abort.
    validate_pins(_stub_router(coverage), ["gpt-oss"])
    assert "researcher" in capsys.readouterr().out


def test_pin_role_coverage_reads_live_only() -> None:
    router = _stub_router(_full_coverage())
    coverage = _pin_role_coverage(router)
    assert coverage["critic"] == ["gpt-oss", "nemotron"]
    assert coverage["researcher"] == ["qwen"]
    # A configured-but-keyless provider is not live and stays out.
    live_snapshot = router.get_available_providers()
    router.config.providers["pz"] = SimpleNamespace(
        models=[SimpleNamespace(id="z", family="zzz", roles=list(PIN_REQUIRED_ROLES))]
    )
    router.get_available_providers = lambda: live_snapshot
    assert "zzz" not in _pin_role_coverage(router).get("solver", [])


async def test_manager_fallback_skips_outside_pins() -> None:
    """Retry walks past a disallowed fallback to the pinned healthy model."""
    from src.orchestration.agent_manager import AgentManager
    from src.providers.mock_provider import MockProvider
    from tests.test_circuit_breaker import _StubDecision

    good = SimpleNamespace(provider_name="mock-b")
    chain = [
        _StubDecision(good, "mock-model", "mock-b", "outer-fam"),
        _StubDecision(good, "mock-model-b", "mock-b", "pinned-fam"),
    ]

    class _WalkRouter:
        def fallback_for(self, decision, error):
            for candidate in chain:
                if (candidate.provider_name, candidate.model) != (
                    decision.provider_name,
                    decision.model,
                ):
                    return candidate
            return None

    flaky = MockProvider(provider_name="mock-a")
    manager = AgentManager(_WalkRouter(), "exec-pin-fallback")
    manager._allowed_families = ["pinned-fam"]
    start = _StubDecision(flaky, "mock-model", "mock-a", "pinned-fam")
    picked = manager._fallback_skipping_open(start, RuntimeError("429"), "solver")
    assert picked is not None
    assert picked.family == "pinned-fam"


async def test_orchestrator_execute_honors_pins(orchestrator) -> None:
    """Pinned run stays inside pins; impossible pins raise loud."""
    from src.providers.router import PinViolationError

    result = await orchestrator.execute(
        execution_id="test-exec-pinned-ok",
        question="What is the mock answer?",
        time_budget_minutes=3,
        allowed_families=["mock"],
    )
    assert result.status == "completed"
    fams = {
        entry.get("family", "")
        for entry in (result.call_log or [])
        if entry.get("total_tokens", 0) > 0
    }
    assert fams <= {"mock"}

    with pytest.raises(PinViolationError):
        await orchestrator.execute(
            execution_id="test-exec-pinned-nope",
            question="What is the mock answer?",
            time_budget_minutes=3,
            allowed_families=["no-such-family"],
        )


async def test_planner_pin_gap_falls_back_without_call() -> None:
    """Planner pins without a planner model → zero-call heuristic plan."""
    from src.orchestration.planner import Planner
    from tests.conftest import MockProvider, MockRouter

    router = MockRouter([MockProvider(provider_name="mock-a")])
    planner = Planner(router)
    plan = await planner.plan("What is the mock answer?", 3, allowed_families=["zzz"])
    assert plan.fallback_used is True


# ── Pin prevention: no out-of-pin model is ever CALLED ───────────────


class _PinWalkRouter:
    """Routes solver/planner/synthesizer to mock-out; fallback walks
    mock-out → mock-outer (family "outer") → mock-in (family "mock")."""

    def __init__(self, out, outer, inn):
        self._providers = {"mock-out": out, "mock-outer": outer, "mock-in": inn}
        self._chain = [
            SimpleNamespace(
                provider=outer, model="m", provider_name="mock-outer", family="outer"
            ),
            SimpleNamespace(
                provider=inn, model="m", provider_name="mock-in", family="mock"
            ),
        ]

    def _decision(self, name):
        provider = self._providers[name]
        family = "mock" if name == "mock-in" else "outer"
        return SimpleNamespace(
            provider=provider,
            model="m",
            provider_name=name,
            family=family,
            role="solver",
            reason="pin-walk",
        )

    def route(self, agent_type="solver", *args, **kwargs):
        return self._decision("mock-out")

    def route_for_planning(self, *args, **kwargs):
        return self._decision("mock-out")

    def route_team(self, team, *args, **kwargs):
        from tests.conftest import MockTeamRouting

        return MockTeamRouting(
            decisions=[self._decision("mock-out") for _ in team],
            families=["outer"],
        )

    def fallback_for(self, decision, error):
        for candidate in self._chain:
            if (candidate.provider_name, candidate.model) != (
                decision.provider_name,
                decision.model,
            ):
                return candidate
        return None

    def get_available_providers(self):
        return list(self._providers)


async def test_agent_validation_retry_never_calls_outside_pins() -> None:
    """Solver malformed twice → agent-level walk skips outer, lands mock-in."""
    from src.agents.solver import SolverAgent
    from src.providers.mock_provider import MockProvider

    out = MockProvider(provider_name="mock-out", always_fail={"solver": "malformed"})
    outer = MockProvider(
        provider_name="mock-outer", always_fail={"solver": "malformed"}
    )
    inn = MockProvider(provider_name="mock-in")
    router = _PinWalkRouter(out, outer, inn)
    agent = SolverAgent(
        agent_id="agent_01",
        provider=out,
        model="m",
        router=router,
        routing=SimpleNamespace(
            provider=out, model="m", provider_name="mock-out", family="outer"
        ),
        family="outer",
        allowed_families=["mock"],
    )
    output = await agent.run("What is the mock answer?")
    assert "42" in output.position
    assert outer.calls == [], "outside-pin fallback must never be called"
    assert len(inn.calls) >= 1
    assert output.family == "mock"


async def test_synthesizer_retry_refuses_outside_pins() -> None:
    """Synthesizer transport failure with only-outside fallback → raise."""
    from src.agents.synthesizer import SynthesizerAgent
    from src.providers.mock_provider import MockProvider, MockRateLimitError

    down = MockProvider(provider_name="mock-out")
    inn = MockProvider(provider_name="mock-in")

    async def _always_429(*args, **kwargs):
        raise MockRateLimitError("Mock 429")

    down.generate = _always_429  # type: ignore[method-assign]

    class _OutsideOnlyRouter:
        def fallback_for(self, decision, error):
            return SimpleNamespace(
                provider=inn, model="m", provider_name="mock-in", family="outer"
            )

    agent = SynthesizerAgent(
        agent_id="agent_09",
        provider=down,
        model="m",
        router=_OutsideOnlyRouter(),
        routing=SimpleNamespace(
            provider=down, model="m", provider_name="mock-out", family="mock"
        ),
        family="mock",
        allowed_families=["mock"],
    )
    with pytest.raises(MockRateLimitError):
        await agent.synthesize(
            question="Q?",
            agent_outputs=[],
            consensus_score=0.5,
            debate_rounds=0,
        )
    assert inn.calls == [], "outside-pin fallback must never be called"


async def test_planner_retry_reuses_pinned_model() -> None:
    """Planner invalid-once → outside fallback refused → same-model retry."""
    from src.orchestration.planner import Planner
    from src.providers.mock_provider import MockProvider

    primary = MockProvider(provider_name="mock-a", fail_next={"plan": "malformed"})
    fallback_provider = MockProvider(provider_name="mock-b")

    class _PlannerPinRouter:
        def route_for_planning(self, *args, **kwargs):
            from tests.conftest import MockAssignment

            return MockAssignment(
                provider=primary,
                model="m",
                provider_name="mock-a",
                role="planner",
                family="mock",
            )

        def fallback_for(self, decision, error):
            from tests.conftest import MockAssignment

            return MockAssignment(
                provider=fallback_provider,
                model="m",
                provider_name="mock-b",
                role="planner",
                family="outer",
            )

    planner = Planner(_PlannerPinRouter())
    plan = await planner.plan("What is the mock answer?", 3, allowed_families=["mock"])
    assert plan.fallback_used is False
    assert fallback_provider.calls == [], "outside-pin planner fallback unused"
    assert len(primary.calls) == 2, "same pinned model retried once"


async def test_manager_retry_agent_carries_pins() -> None:
    """Transport retry rebuild keeps pins for the agent-level fallback."""
    from src.orchestration.agent_manager import AgentManager
    from src.providers.mock_provider import MockProvider

    flaky = MockProvider(provider_name="mock-a", always_fail={"solver": "rate_limit"})
    healthy = MockProvider(provider_name="mock-b")
    router = _PinWalkRouter(flaky, healthy, healthy)
    manager = AgentManager(router, "exec-pin-carry")
    manager._allowed_families = ["mock"]
    agent = manager._instantiate(
        {"agent_type": "solver", "role_description": "s"},
        SimpleNamespace(
            provider=flaky,
            model="m",
            provider_name="mock-a",
            family="outer",
        ),
        agent_id="agent_01",
    )
    assert agent._allowed_families == ["mock"]
    assert manager.agents["agent_01"]._allowed_families == ["mock"]
