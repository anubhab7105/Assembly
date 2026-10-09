"""Family-aware routing tests: distinctness, fallback order, degraded modes.

Custom catalogs come from tmp models.yaml files with fresh limiters —
no network, no shared state.
"""

from types import SimpleNamespace

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from src.api.executions import _persist_agent_runs
from src.database.base import Base
from src.database.models import AgentRun, QuotaUsage
from src.orchestration.agent_manager import AgentManager
from src.providers.config import load_models_config
from src.providers.errors import RateLimited
from src.providers.mock_provider import MockProvider
from src.providers.quota import QuotaLimiter, fingerprint_key
from src.providers.router import ModelRouter, RoutingDecision
from tests.conftest import make_models_yaml

ALL_ROLES = ["solver", "critic", "researcher", "synthesizer", "planner"]
SOLVER_ROLES = ["solver", "critic", "planner"]


def _fam4() -> dict:
    """Four providers, four distinct families (all limits filled)."""
    return {
        "pa": [{"id": "pa-fast", "family": "gpt-oss", "roles": list(ALL_ROLES)}],
        "pb": [{"id": "pb-strong", "family": "qwen", "roles": list(ALL_ROLES)}],
        "pc": [{"id": "pc-flash", "family": "gemini", "roles": list(ALL_ROLES)}],
        "pd": [{"id": "pd-chat", "family": "mistral", "roles": list(ALL_ROLES)}],
    }


def _fam2() -> dict:
    """Two families across three providers (all limits filled)."""
    return {
        "pa": [{"id": "pa-fast", "family": "gpt-oss", "roles": list(SOLVER_ROLES)}],
        "pb": [{"id": "pb-strong", "family": "gpt-oss", "roles": list(SOLVER_ROLES)}],
        "pc": [{"id": "pc-flash", "family": "qwen", "roles": list(SOLVER_ROLES)}],
    }


def _fam1() -> dict:
    """One family everywhere (all limits filled)."""
    return {
        "pa": [{"id": "pa-fast", "family": "gpt-oss", "roles": list(SOLVER_ROLES)}],
        "pb": [{"id": "pb-strong", "family": "gpt-oss", "roles": list(SOLVER_ROLES)}],
        "pc": [{"id": "pc-flash", "family": "gpt-oss", "roles": list(SOLVER_ROLES)}],
    }


def _router(tmp_path, providers, keys, **kwargs):
    path = make_models_yaml(tmp_path, providers)
    config = load_models_config(path)
    limiter = QuotaLimiter(config=config, **kwargs)
    return ModelRouter(config=config, keys=keys, limiter=limiter), limiter


def _team(*agent_types):
    return [
        {"agent_type": kind, "role_description": f"{kind} role"} for kind in agent_types
    ]


# ── Family distinctness ─────────────────────────────────────────────


def test_solvers_spread_across_distinct_families(tmp_path) -> None:
    router, _ = _router(
        tmp_path, _fam4(), {"pa": "k1", "pb": "k2", "pc": "k3", "pd": "k4"}
    )
    routing = router.route_team(_team("solver", "solver", "solver"))
    assert not routing.degraded and routing.warnings == []
    assert [d.family for d in routing.decisions] == ["gpt-oss", "qwen", "gemini"]
    assert len({d.provider_name for d in routing.decisions}) == 3
    assert all(d.reason for d in routing.decisions)


def test_fourth_solver_reuses_with_warning(tmp_path) -> None:
    router, _ = _router(tmp_path, _fam4(), {"pa": "k1", "pb": "k2", "pc": "k3"})
    routing = router.route_team(_team("solver", "solver", "solver", "solver"))
    families = [d.family for d in routing.decisions]
    assert len(set(families[:3])) == 3
    assert families[3] in families[:3]
    assert any("reused" in w for w in routing.warnings)


def test_critic_avoids_solver_families(tmp_path) -> None:
    router, _ = _router(
        tmp_path, _fam4(), {"pa": "k1", "pb": "k2", "pc": "k3", "pd": "k4"}
    )
    routing = router.route_team(_team("solver", "solver", "critic"))
    solver_families = {d.family for d in routing.decisions[:2]}
    critic = routing.decisions[2]
    assert critic.family not in solver_families


def test_critic_forced_when_no_spare_family(tmp_path) -> None:
    router, _ = _router(tmp_path, _fam2(), {"pa": "k1", "pb": "k2", "pc": "k3"})
    routing = router.route_team(_team("solver", "solver", "critic"))
    solver_families = {d.family for d in routing.decisions[:2]}
    assert solver_families == {"gpt-oss", "qwen"}
    critic = routing.decisions[2]
    assert critic.family in solver_families
    assert "reviewed" in critic.reason


# ── Degraded modes ──────────────────────────────────────────────────


def test_two_families_warn_but_proceed(tmp_path) -> None:
    router, _ = _router(tmp_path, _fam2(), {"pa": "k1", "pb": "k2", "pc": "k3"})
    routing = router.route_team(_team("solver", "critic"))
    assert not routing.degraded
    assert routing.warnings != []
    assert len(routing.decisions) == 2


def test_single_family_returns_degraded_flag(tmp_path) -> None:
    router, _ = _router(tmp_path, _fam1(), {"pa": "k1", "pb": "k2", "pc": "k3"})
    routing = router.route_team(_team("solver", "critic"))
    assert routing.degraded
    assert routing.warnings != []
    assert [d.family for d in routing.decisions] == ["gpt-oss", "gpt-oss"]


# ── Fallback chains ─────────────────────────────────────────────────


def test_fallback_prefers_different_family(tmp_path) -> None:
    router, _ = _router(
        tmp_path, _fam4(), {"pa": "k1", "pb": "k2", "pc": "k3", "pd": "k4"}
    )
    first = router.route("solver")
    assert (first.provider_name, first.family) == ("pa", "gpt-oss")
    fallback = router.fallback_for(first, RateLimited("pa", "slow"))
    assert fallback is not None
    assert fallback.family == "qwen"
    assert fallback.provider_name == "pb"
    assert (fallback.provider_name, fallback.model) != ("pa", "pa-fast")
    assert "RateLimited" in fallback.reason


def test_fallback_same_family_other_provider_when_only_option(tmp_path) -> None:
    router, limiter = _router(tmp_path, _fam2(), {"pa": "k1", "pb": "k2", "pc": "k3"})
    first = router.route("solver")
    assert first.provider_name == "pa"
    limiter.report_429("pc", fingerprint_key("k3"), "pc-flash", retry_after=60.0)
    fallback = router.fallback_for(first, RateLimited("pa", "slow"))
    assert fallback is not None
    assert fallback.provider_name == "pb"
    assert fallback.family == "gpt-oss"


def test_fallback_none_when_everything_exhausted(tmp_path) -> None:
    router, limiter = _router(
        tmp_path, _fam4(), {"pa": "k1", "pb": "k2", "pc": "k3", "pd": "k4"}
    )
    first = router.route("solver")
    for pid, key, model in (
        ("pb", "k2", "pb-strong"),
        ("pc", "k3", "pc-flash"),
        ("pd", "k4", "pd-chat"),
    ):
        limiter.report_429(pid, fingerprint_key(key), model, retry_after=60.0)
    assert router.fallback_for(first, RateLimited("pa", "slow")) is None


# ── Quota-aware routing ─────────────────────────────────────────────


def test_quota_spent_provider_skipped(tmp_path, monkeypatch) -> None:
    import src.providers.quota as quota_mod

    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    Base.metadata.create_all(bind=engine)
    factory = sessionmaker(bind=engine)
    providers = _fam4()
    providers["pa"][0]["limits"] = {"rpm": 100, "rpd": 1}
    path = make_models_yaml(tmp_path, providers)
    config = load_models_config(path)
    limiter = QuotaLimiter(config=config, session_factory=factory)
    router = ModelRouter(
        config=config,
        keys={"pa": "k1", "pb": "k2", "pc": "k3", "pd": "k4"},
        limiter=limiter,
    )

    monkeypatch.setattr(quota_mod, "today_str", lambda: "2099-01-01")
    db = factory()
    db.add(
        QuotaUsage(
            provider="pa",
            key_fingerprint=fingerprint_key("k1"),
            day="2099-01-01",
            model_id="pa-fast",
            count=1,
        )
    )
    db.commit()
    db.close()

    routing = router.route_team(_team("solver", "critic"))
    assert "pa" not in [d.provider_name for d in routing.decisions]


# ── Decision provenance + retry integration ─────────────────────────


def test_agent_run_persistence_helper() -> None:
    engine = create_engine("sqlite://")
    Base.metadata.create_all(bind=engine)
    db = sessionmaker(bind=engine)()
    _persist_agent_runs(
        db,
        "exec-1",
        [
            {
                "agent_type": "solver",
                "role_description": "r",
                "model": "m",
                "provider_name": "pa",
            }
        ],
    )
    db.commit()
    rows = db.query(AgentRun).all()
    assert len(rows) == 1
    assert (rows[0].execution_id, rows[0].model, rows[0].provider) == (
        "exec-1",
        "m",
        "pa",
    )
    db.close()


async def test_retry_on_rate_limit_uses_fallback_provider() -> None:
    failing = MockProvider(provider_name="mock-a")
    healthy = MockProvider(provider_name="mock-b")
    calls = {"failing": 0}
    original_generate = failing.generate

    async def flaky_generate(*args, **kwargs):
        calls["failing"] += 1
        if calls["failing"] == 1:
            raise RateLimited("mock-a", "slow")
        return await original_generate(*args, **kwargs)

    failing.generate = flaky_generate

    decision_a = RoutingDecision(
        provider=failing,
        model="m",
        provider_name="mock-a",
        family="fam-a",
        role="solver",
        reason="test",
    )
    decision_b = RoutingDecision(
        provider=healthy,
        model="m",
        provider_name="mock-b",
        family="fam-b",
        role="critic",
        reason="test",
    )

    class StubRouter:
        def route_team(self, team, *args, **kwargs):
            by_role = {"solver": decision_a, "critic": decision_b}
            return SimpleNamespace(
                decisions=[by_role[s["agent_type"]] for s in team],
                warnings=[],
                degraded=False,
                families=["fam-a", "fam-b"],
            )

        def fallback_for(self, decision, error):
            assert isinstance(error, RateLimited)
            return RoutingDecision(
                provider=healthy,
                model="m",
                provider_name="mock-b",
                family="fam-b",
                role=decision.role,
                reason="test fallback",
            )

    manager = AgentManager(StubRouter(), "exec-retry")
    agents = manager.create_team([{"agent_type": "solver", "role_description": "s"}])
    outputs = await manager.run_all_independent(agents, "What is the answer?")
    assert "42" in outputs[0].position
    assert calls["failing"] == 1  # wrapper raised once; retry ran on healthy
    assert len(healthy.calls) == 1
    assert manager.agents["agent_01"].provider is healthy


async def test_orchestrator_records_routing(orchestrator) -> None:
    result = await orchestrator.execute(
        execution_id="test-routing-record",
        question="What is the mock answer?",
        time_budget_minutes=3,
    )
    assert result.status == "completed"
    assert result.routing != []
    assert all(entry["reason"] for entry in result.routing)
    assert result.degraded is False
    assert result.warnings == []
