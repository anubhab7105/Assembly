"""Capacity planner tests (docs/WORKFLOW.md section 4).

All pure-function tests: KeyBudget counts in, TeamPlan out — no providers,
no network, no database. Endpoint tests stub the router snapshot so the
preflight route stays offline too.
"""

from types import SimpleNamespace

import pytest

from src.orchestration.capacity import (
    KeyBudget,
    PlannerSuggestion,
    affordable_calls,
    can_start_round,
    cost_of_plan,
    estimated_seconds,
    heuristic_suggestion,
    plan_capacity,
    synth_reserve_seconds,
)

# WORKFLOW section 4 approx-call ranges per tier.
TIER_CALL_RANGES = {3: (8, 12), 5: (15, 22), 10: (25, 40), 15: (40, 60)}

#: A demanding planner wish: clipped to each tier's ceilings it reproduces
#: the WORKFLOW table midpoints (with needs_research=True).
GENEROUS = PlannerSuggestion(
    roles=("solver", "solver", "researcher", "critic", "solver", "solver"),
    complexity="high",
    needs_research=True,
    estimated_rounds=5,
)


def _many_keys(n: int = 5, rpm: int = 30, rpd: int = 1000) -> list[KeyBudget]:
    return [
        KeyBudget(provider=f"p{i}", rpm_limit=rpm, rpd_remaining=rpd) for i in range(n)
    ]


# ── Formula units ───────────────────────────────────────────────────


def test_synth_reserve_is_max_of_25s_and_12_percent() -> None:
    assert synth_reserve_seconds(3) == pytest.approx(25.0)  # 12% of 180s = 21.6s
    assert synth_reserve_seconds(5) == pytest.approx(36.0)
    assert synth_reserve_seconds(10) == pytest.approx(72.0)
    assert synth_reserve_seconds(15) == pytest.approx(108.0)


def test_safety_margin_keeps_30_percent() -> None:
    # One key: min(10 rpm x 3 min, huge rpd) = 30 calls -> 30 x 0.7 = 21.
    assert (
        affordable_calls(
            [KeyBudget(provider="p", rpm_limit=10, rpd_remaining=10_000)], 3
        )
        == 21
    )


def test_affordable_prefers_tighter_side() -> None:
    # rpm allows 30 x 5 = 150, but only 20 left today -> 20 x 0.7 = 14.
    assert (
        affordable_calls([KeyBudget(provider="p", rpm_limit=30, rpd_remaining=20)], 5)
        == 14
    )


def test_affordable_token_options_bind() -> None:
    # tpm 8000 x 5 min / 2000 tokens-per-call = 20 calls: binds over rpm/rpd.
    assert affordable_calls(
        [KeyBudget(provider="g", rpm_limit=30, rpd_remaining=1000, tpm_limit=8000)],
        5,
    ) == int(min(150, 1000, 20) * 0.7)
    # tpd remaining 5000 tokens / 2000 = 2 calls: binds on its own.
    assert affordable_calls([KeyBudget(provider="g", tpd_remaining=5000)], 5) == int(
        2 * 0.7
    )
    # Absent token budgets change nothing (old math preserved).
    assert (
        affordable_calls([KeyBudget(provider="p", rpm_limit=30, rpd_remaining=20)], 5)
        == 14
    )


REACT_QUESTION = (
    "Is React better than Vue for a large cybersecurity platform? "
    "Compare ecosystem, performance, state management at scale, and hiring."
)


def test_groq_tpm_downsizes_five_minute_plan() -> None:
    """One groq-like bucket: tpm 8000 (20 calls/5 min) binds below the
    tier-5 standard cost of 18, so the plan downgrades with an explanation."""
    keys = [
        KeyBudget(provider="groq", rpm_limit=30, rpd_remaining=1000, tpm_limit=8000)
    ]
    plan = plan_capacity(keys, 5, heuristic_suggestion(REACT_QUESTION))
    assert plan.affordable_calls == int(min(150, 1000, 20) * 0.7) == 14
    assert plan.downgraded and plan.feasible
    assert plan.feasible_tier == 3
    assert plan.explanation


def test_groq_three_buckets_sum_but_stay_tpm_bound() -> None:
    """Three model-scope buckets sum — yet tpm still binds, not rpm:
    3 x 14 = 42, where rpm alone would allow 3 x 105 = 315."""
    keys = [
        KeyBudget(provider="groq", rpm_limit=30, rpd_remaining=1000, tpm_limit=8000)
        for _ in range(3)
    ]
    assert affordable_calls(keys, 5) == 42


def test_affordable_unknown_limits_is_unlimited() -> None:
    assert affordable_calls([KeyBudget(provider="p")], 5) is None
    assert affordable_calls([], 5) == 0  # no keys at all: nothing affordable


def test_cost_formula_matches_workflow() -> None:
    # agents x solve + rounds x agents x critique + searches + planner + synth.
    assert cost_of_plan(3, 1, 2) == 3 + 3 + 2 + 2 == 10
    assert cost_of_plan(4, 2, 4) == 4 + 8 + 4 + 2 == 18


def test_can_start_round_needs_round_plus_reserve() -> None:
    assert can_start_round(100.0, 3)  # 30s round + 25s reserve fits in 100s
    assert not can_start_round(50.0, 3)  # 50 < 30 + 25


def test_invalid_tier_rejected() -> None:
    with pytest.raises(ValueError, match="Unknown time tier"):
        plan_capacity(_many_keys(), 7, GENEROUS)


# ── Each tier with ample quota ────────────────────────────────────────


@pytest.mark.parametrize("tier", [3, 5, 10, 15])
def test_each_tier_feasible_with_many_keys(tier: int) -> None:
    plan = plan_capacity(_many_keys(), tier, GENEROUS)
    assert plan.feasible and not plan.downgraded
    assert plan.feasible_tier == tier == plan.requested_tier
    low, high = TIER_CALL_RANGES[tier]
    assert low <= plan.estimated_calls <= high
    assert plan.estimated_seconds <= tier * 60
    assert plan.estimated_seconds == pytest.approx(
        estimated_seconds(plan.agents, plan.rounds, plan.search_budget)
    )
    assert plan.synth_reserve_seconds == pytest.approx(synth_reserve_seconds(tier))
    assert plan.explanation  # human-readable verdict always present


def test_many_key_plan_uses_full_team() -> None:
    plan = plan_capacity(_many_keys(), 5, GENEROUS)
    assert (plan.agents, plan.rounds, plan.search_budget) == (4, 2, 4)


# ── Many-key vs few-key ───────────────────────────────────────────────


def test_many_keys_fit_largest_tier() -> None:
    plan = plan_capacity(_many_keys(n=5), 15, GENEROUS)
    assert plan.feasible and plan.feasible_tier == 15
    assert plan.affordable_calls == int(5 * min(30 * 15, 1000) * 0.7)


def test_few_keys_downgrade_to_smaller_tier_with_explanation() -> None:
    # One thin key: min(2 rpm x 15 min, 11 rpd) = 11 -> 7 affordable calls.
    # No tier standard fits (3-minute standard needs 10), so the 3-minute
    # team is trimmed to the minimum (2,1,0) = 6 calls.
    thin = [KeyBudget(provider="solo", rpm_limit=2, rpd_remaining=11)]
    plan = plan_capacity(thin, 15, GENEROUS)
    assert plan.affordable_calls == 7
    assert plan.feasible and plan.downgraded
    assert plan.feasible_tier == 3
    assert plan.estimated_calls <= 7
    assert "15-minute tier is not feasible" in plan.explanation
    assert "3-minute plan" in plan.explanation
    assert plan.warnings != ()


def test_partial_quota_falls_back_to_smaller_tier_standard() -> None:
    # min(2 rpm x 15 min, 20 rpd) = 20 -> 14 affordable calls: the 15/10/5
    # standards (48/35/18) miss, but the 3-minute standard (3,1,2) = 10 fits.
    thin = [KeyBudget(provider="solo", rpm_limit=2, rpd_remaining=20)]
    plan = plan_capacity(thin, 15, GENEROUS)
    assert plan.affordable_calls == 14
    assert plan.feasible and plan.downgraded
    assert plan.feasible_tier == 3
    assert (plan.agents, plan.rounds, plan.search_budget) == (3, 1, 2)
    assert any("15-minute tier needs" in w for w in plan.warnings)


# ── Exhausted quota ───────────────────────────────────────────────────


def test_exhausted_daily_quota_is_infeasible() -> None:
    spent = [
        KeyBudget(provider=f"p{i}", rpm_limit=30, rpd_remaining=0) for i in range(4)
    ]
    plan = plan_capacity(spent, 5, GENEROUS)
    assert not plan.feasible
    assert plan.affordable_calls == 0
    assert "quota" in plan.explanation.lower()
    assert plan.warnings != ()


def test_cooling_but_unlimited_keys_stay_feasible() -> None:
    plan = plan_capacity([KeyBudget(provider="p")], 3, GENEROUS)
    assert plan.feasible and plan.affordable_calls is None
    assert any("unknown" in w.lower() for w in plan.warnings)


# ── Heuristic suggestion ──────────────────────────────────────────────


def test_heuristic_short_question_is_low() -> None:
    suggestion = heuristic_suggestion("What is 2+2?")
    assert suggestion.complexity == "low"
    assert not suggestion.needs_research
    assert len(suggestion.roles) == 2


def test_heuristic_comparison_needs_research() -> None:
    suggestion = heuristic_suggestion("Is React better than Vue for a large platform?")
    assert suggestion.needs_research
    assert suggestion.complexity == "medium"


def test_heuristic_long_research_question_is_high() -> None:
    question = (
        "Compare the latest large language model ecosystems and market evidence "
        "across all major vendors with sources and benchmarks and hiring data "
        "and inference pricing and long term vendor lock in risks in detail "
        "with migration costs and team training implications and compliance "
        "requirements and security audits and support contracts"
    )
    suggestion = heuristic_suggestion(question)
    assert suggestion.complexity == "high"
    assert suggestion.needs_research


# ── No key material in plans ──────────────────────────────────────────


def test_plan_output_carries_no_secrets(fake_key: str) -> None:
    plan = plan_capacity(_many_keys(), 5, GENEROUS)
    assert fake_key not in str(plan.to_dict())
    assert "provider_keys" not in str(plan.to_dict())
    assert set(plan.to_dict()) == {
        "agents",
        "rounds",
        "search_budget",
        "estimated_calls",
        "estimated_seconds",
        "warnings",
        "feasible_tier",
        "requested_tier",
        "feasible",
        "downgraded",
        "affordable_calls",
        "synth_reserve_seconds",
        "explanation",
    }


# ── Preflight endpoint (router stubbed, fully offline) ────────────────


def _authed_client(monkeypatch):
    from fastapi.testclient import TestClient
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker
    from sqlalchemy.pool import StaticPool

    import src.api.executions as exec_mod
    from src.core.config import settings
    from src.database.base import Base, get_db
    from src.main import app

    monkeypatch.setattr(settings, "app_mode", "web")

    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    testing_session = sessionmaker(bind=engine)
    Base.metadata.create_all(bind=engine)

    def override_get_db():
        db = testing_session()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = override_get_db
    monkeypatch.setattr(exec_mod, "SessionLocal", testing_session)
    client = TestClient(app)
    signup = client.post(
        "/api/auth/signup",
        json={
            "email": "preflight@test.local",
            "name": "Pre",
            "password": "password123",
        },
    )
    assert signup.status_code == 200, signup.text
    client.headers.update({"Authorization": f"Bearer {signup.json()['access_token']}"})
    return client, exec_mod


def _stub_router(monkeypatch, exec_mod, snapshot):
    router = SimpleNamespace(
        quota_snapshot=lambda: snapshot,
        available_families=lambda: ["gemini", "qwen", "gpt-oss"],
    )
    monkeypatch.setattr(exec_mod._orchestrator, "router", router)


def test_preflight_returns_plan_without_running(monkeypatch) -> None:
    client, exec_mod = _authed_client(monkeypatch)
    _stub_router(
        monkeypatch,
        exec_mod,
        [
            {
                "provider": f"p{i}",
                "rpm_limit": 30,
                "rpd_remaining": 1000,
                "cooldown_seconds": 0.0,
            }
            for i in range(5)
        ],
    )
    response = client.get(
        "/api/executions/preflight",
        params={"question": "Is React better than Vue?", "time_budget_minutes": 5},
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["feasible"] is True
    assert body["requested_tier"] == 5 == body["feasible_tier"]
    assert body["agents"] >= 2 and body["estimated_calls"] > 0
    assert body["explanation"] != ""
    assert body["usable_keys"] == 5
    assert body["providers"] == [f"p{i}" for i in range(5)]
    assert "provider_keys" not in response.text


def test_preflight_reports_fallback_on_thin_quota(monkeypatch) -> None:
    client, exec_mod = _authed_client(monkeypatch)
    _stub_router(
        monkeypatch,
        exec_mod,
        [
            {
                "provider": "solo",
                "rpm_limit": 2,
                "rpd_remaining": 11,
                "cooldown_seconds": 0.0,
            }
        ],
    )
    response = client.get(
        "/api/executions/preflight",
        params={"question": "Is React better than Vue?", "time_budget_minutes": 15},
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["feasible"] is True and body["downgraded"] is True
    assert body["feasible_tier"] < 15


def test_preflight_exhausted_quota_is_infeasible(monkeypatch) -> None:
    client, exec_mod = _authed_client(monkeypatch)
    _stub_router(
        monkeypatch,
        exec_mod,
        [
            {
                "provider": f"p{i}",
                "rpm_limit": 30,
                "rpd_remaining": 0,
                "cooldown_seconds": 0.0,
            }
            for i in range(3)
        ],
    )
    response = client.get(
        "/api/executions/preflight",
        params={"question": "What is 2+2?", "time_budget_minutes": 3},
    )
    assert response.status_code == 200, response.text
    assert response.json()["feasible"] is False


def test_preflight_rejects_bad_tier_and_needs_auth(monkeypatch) -> None:
    client, _ = _authed_client(monkeypatch)
    bad_tier = client.get(
        "/api/executions/preflight",
        params={"question": "Hi?", "time_budget_minutes": 7},
    )
    assert bad_tier.status_code == 400
    client.headers.pop("Authorization")
    denied = client.get(
        "/api/executions/preflight",
        params={"question": "Hi?", "time_budget_minutes": 3},
    )
    assert denied.status_code in (401, 403)
