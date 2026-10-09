"""Planner tests (docs/WORKFLOW.md section 3).

Mock providers only — no network. Covers: valid WORKFLOW-shape output,
malformed/empty/invalid replies (exactly one retry, then the heuristic
fallback), legacy team-shape translation, capacity caps, the heuristic
classifier, and a key-leak scan.
"""

import json
from types import SimpleNamespace
from typing import Any

from src.orchestration.planner import Planner, PlanSchema
from src.providers.mock_provider import MockProvider

VALID_PLAN = {
    "problem_type": "research",
    "complexity": "high",
    "needs_research": True,
    "needs_code_execution": False,
    "suggested_roles": ["solver", "solver", "researcher", "critic"],
    "estimated_rounds": 3,
}

LEGACY_PLAN = {
    "problem_type": "general",
    "complexity": "medium",
    "needs_research": False,
    "team": [
        {"agent_type": "solver", "role_description": "Problem solver"},
        {"agent_type": "critic", "role_description": "Answer verifier"},
    ],
    "reasoning": "Mock plan.",
}


def _stub_router(
    provider: MockProvider,
    **extra: Any,
) -> SimpleNamespace:
    """Duck-typed router: only what Planner touches."""
    return SimpleNamespace(
        route_for_planning=lambda: SimpleNamespace(
            provider=provider,
            model="mock-model",
            provider_name="mock-a",
            family="mock",
            role="planner",
            reason="test routing",
        ),
        **extra,
    )


def _planner(
    plan_script: dict[str, Any] | str,
    budget: int = 5,
    provider_kwargs: dict[str, Any] | None = None,
    **router_extra: Any,
) -> tuple[Planner, MockProvider, int]:
    provider = MockProvider(
        scripts={"plan": plan_script},
        provider_name="mock-a",
        **(provider_kwargs or {}),
    )
    return Planner(_stub_router(provider, **router_extra)), provider, budget


# ── Valid responses ───────────────────────────────────────────────────


async def test_valid_workflow_shape() -> None:
    planner, provider, budget = _planner(VALID_PLAN)
    plan = await planner.plan("Compare React and Vue ecosystems.", budget)

    assert plan.problem_type == "research"
    assert plan.complexity == "high"
    assert plan.needs_research is True
    assert plan.needs_code_execution is False
    assert plan.suggested_roles == ["solver", "solver", "researcher", "critic"]
    assert plan.estimated_rounds == 3  # 5-min ceiling is 3 rounds (early-stop via consensus)
    assert [m["agent_type"] for m in plan.team_composition] == plan.suggested_roles
    assert plan.fallback_used is False
    assert len(provider.calls) == 1  # no retry needed


async def test_valid_bare_json_with_surrounding_prose() -> None:
    raw = (
        "Here is my classification:\n```json\n"
        + json.dumps(VALID_PLAN)
        + "\n```\nHope this helps."
    )
    planner, provider, _ = _planner(raw, budget=15)
    plan = await planner.plan("Compare React and Vue ecosystems.", 15)

    assert plan.suggested_roles == ["solver", "solver", "researcher", "critic"]
    assert plan.estimated_rounds == 3
    assert len(provider.calls) == 1


async def test_legacy_team_shape_translated() -> None:
    planner, _, _ = _planner(LEGACY_PLAN)
    plan = await planner.plan("What is the mock answer?", 3)

    assert plan.suggested_roles == ["solver", "critic"]
    assert [m["agent_type"] for m in plan.team_composition] == ["solver", "critic"]
    assert plan.reasoning == "Mock plan."
    assert plan.fallback_used is False


async def test_unknown_problem_type_normalized() -> None:
    planner, _, _ = _planner({**VALID_PLAN, "problem_type": "technical_comparison"})
    plan = await planner.plan("Compare X and Y.", 15)

    assert plan.problem_type == "general"
    assert plan.fallback_used is False


def test_schema_defaults() -> None:
    schema = PlanSchema.model_validate({})
    assert schema.problem_type == "general"
    assert schema.complexity == "medium"
    assert schema.needs_research is False
    assert schema.suggested_roles == ["solver", "critic"]
    assert schema.estimated_rounds == 1


# ── Malformed / empty / invalid: one retry, then fallback ─────────────


async def test_malformed_then_valid_uses_single_retry() -> None:
    planner, provider, _ = _planner(
        VALID_PLAN, budget=15, provider_kwargs={"fail_next": {"plan": "malformed"}}
    )
    plan = await planner.plan("Compare React and Vue ecosystems.", 15)

    assert plan.suggested_roles == ["solver", "solver", "researcher", "critic"]
    assert plan.fallback_used is False
    assert len(provider.calls) == 2


async def test_persistently_malformed_uses_fallback() -> None:
    planner, provider, _ = _planner(
        VALID_PLAN, provider_kwargs={"always_fail": {"plan": "malformed"}}
    )
    plan = await planner.plan("Is React better than Vue for a large platform?", 5)

    assert len(provider.calls) == 2  # initial + exactly one retry
    assert plan.fallback_used is True
    assert "Heuristic fallback" in plan.reasoning
    assert plan.suggested_roles != []
    assert all(r in ("solver", "researcher", "critic") for r in plan.suggested_roles)
    # Heuristic sees a comparison question: research-flavoured, medium.
    assert plan.needs_research is True
    assert plan.complexity == "medium"


async def test_empty_response_uses_fallback() -> None:
    planner, provider, _ = _planner("")
    plan = await planner.plan("What is 2+2?", 3)

    assert len(provider.calls) == 2
    assert plan.fallback_used is True
    assert plan.suggested_roles == ["solver", "critic"]
    assert plan.complexity == "low"


async def test_invalid_schema_retries_then_falls_back() -> None:
    bad = {
        "problem_type": "general",
        "complexity": "extreme",
        "needs_research": "maybe",
        "suggested_roles": ["wizard"],
        "estimated_rounds": 0,
    }
    planner, provider, _ = _planner(bad)
    plan = await planner.plan("What is 2+2?", 3)

    assert len(provider.calls) == 2
    assert plan.fallback_used is True
    assert len(plan.team_composition) == 2


async def test_empty_roles_list_is_invalid() -> None:
    planner, provider, _ = _planner({"complexity": "low", "suggested_roles": []})
    plan = await planner.plan("Hi?", 3)

    assert len(provider.calls) == 2
    assert plan.fallback_used is True


async def test_provider_error_goes_straight_to_fallback() -> None:
    planner, provider, _ = _planner(
        VALID_PLAN, provider_kwargs={"always_fail": {"plan": "timeout"}}
    )
    plan = await planner.plan("What is 2+2?", 3)

    assert len(provider.calls) == 1  # transport errors are not retried
    assert plan.fallback_used is True


async def test_retry_prefers_fallback_model() -> None:
    primary = MockProvider(
        scripts={"plan": VALID_PLAN},
        always_fail={"plan": "malformed"},
        provider_name="mock-a",
    )
    fallback = MockProvider(scripts={"plan": VALID_PLAN}, provider_name="mock-b")
    router = _stub_router(
        primary,
        fallback_for=lambda _assignment, _error: SimpleNamespace(
            provider=fallback,
            model="mock-model-b",
            provider_name="mock-b",
            family="other",
            role="planner",
            reason="test fallback",
        ),
    )
    plan = await Planner(router).plan("Compare React and Vue ecosystems.", 15)

    assert len(primary.calls) == 1
    assert len(fallback.calls) == 1
    assert plan.fallback_used is False
    assert plan.suggested_roles == ["solver", "solver", "researcher", "critic"]


async def test_routing_failure_uses_fallback() -> None:
    def _boom() -> Any:
        raise RuntimeError("no live providers")

    plan = await Planner(SimpleNamespace(route_for_planning=_boom)).plan("Hi?", 3)

    assert plan.fallback_used is True
    assert len(plan.team_composition) == 2


# ── Capacity caps ─────────────────────────────────────────────────────


async def test_roles_capped_by_tier_ceiling() -> None:
    big = {**VALID_PLAN, "suggested_roles": ["solver"] * 6, "estimated_rounds": 5}
    planner, _, _ = _planner(big)
    plan = await planner.plan("A huge complex question.", 3)

    assert len(plan.team_composition) == 3  # 3-min ceiling
    assert plan.estimated_rounds == 1
    assert plan.fallback_used is False


async def test_quota_snapshot_trims_to_affordable_team() -> None:
    thin = [{"provider": "solo", "rpm_limit": 2, "rpd_remaining": 11}]
    planner, _, _ = _planner(VALID_PLAN, budget=15, quota_snapshot=lambda: thin)
    plan = await planner.plan("Compare React and Vue ecosystems.", 15)

    assert plan.fallback_used is False
    assert len(plan.team_composition) == 2
    assert "Capacity trim" in plan.reasoning


async def test_infeasible_quota_keeps_tier_team_with_warning() -> None:
    spent = [{"provider": "solo", "rpm_limit": 2, "rpd_remaining": 0}]
    planner, _, _ = _planner(VALID_PLAN, budget=5, quota_snapshot=lambda: spent)
    plan = await planner.plan("Compare React and Vue ecosystems.", 5)

    assert plan.fallback_used is False
    assert len(plan.team_composition) == 4  # tier-clipped team kept
    assert "Capacity warning" in plan.reasoning


# ── Heuristic classifier ──────────────────────────────────────────────


async def test_heuristic_problem_types() -> None:
    planner, _, _ = _planner("", provider_kwargs={"always_fail": {"plan": "malformed"}})

    math = await planner.plan("Calculate the integral of x squared.", 5)
    assert math.problem_type == "math"
    assert math.needs_code_execution is True

    coding = await planner.plan("Write a python function to debug this.", 5)
    assert coding.problem_type == "coding"

    steps = await planner.plan("Give me a step by step project plan.", 5)
    assert steps.problem_type == "multi_step"

    research = await planner.plan("What is the latest evidence on sleep?", 5)
    assert research.problem_type == "research"
    assert research.needs_research is True


async def test_heuristic_handles_empty_question() -> None:
    planner, _, _ = _planner("", provider_kwargs={"always_fail": {"plan": "malformed"}})
    plan = await planner.plan("", 3)

    assert plan.fallback_used is True
    assert plan.problem_type == "general"
    assert plan.complexity == "low"
    assert len(plan.team_composition) == 2


# ── Research OR-rule (LLM false + heuristic true → research) ─────────


def _llm_says_no_research() -> dict:
    return {
        "problem_type": "general",
        "complexity": "medium",
        "needs_research": False,
        "needs_code_execution": False,
        "suggested_roles": ["solver", "critic"],
        "estimated_rounds": 1,
    }


async def test_or_rule_rescues_comparative_question() -> None:
    planner, _, _ = _planner(_llm_says_no_research())
    plan = await planner.plan("Is React better than Vue for a large platform?", 5)

    assert plan.needs_research is True
    assert "researcher" in plan.suggested_roles
    assert "heuristic" in plan.reasoning


async def test_or_rule_rescues_evidence_seeking_question() -> None:
    planner, _, _ = _planner(_llm_says_no_research())
    plan = await planner.plan(
        "What evidence shows this library is production ready?", 5
    )

    assert plan.needs_research is True
    assert "researcher" in plan.suggested_roles


async def test_or_rule_rescues_time_sensitive_question() -> None:
    planner, _, _ = _planner(_llm_says_no_research())
    plan = await planner.plan(
        "What are the latest Python release highlights in 2026?", 5
    )

    assert plan.needs_research is True
    assert "researcher" in plan.suggested_roles


async def test_or_rule_keeps_llm_true_without_duplicating_researcher() -> None:
    planner, _, _ = _planner(VALID_PLAN)
    plan = await planner.plan("Compare React and Vue ecosystems.", 5)

    assert plan.needs_research is True
    assert plan.suggested_roles.count("researcher") == 1


async def test_or_rule_stays_quiet_without_any_signal() -> None:
    planner, _, _ = _planner(_llm_says_no_research())
    plan = await planner.plan("What is 2+2?", 5)

    assert plan.needs_research is False
    assert "researcher" not in plan.suggested_roles
    assert "heuristic" not in plan.reasoning


# ── Key-leak scan ─────────────────────────────────────────────────────


async def test_fake_key_absent_from_plan_and_logs(fake_key: str, caplog: Any) -> None:
    import logging

    planner, _, _ = _planner(VALID_PLAN)
    with caplog.at_level(logging.INFO, logger="assembly"):
        plan = await planner.plan(f"Compare X and Y {fake_key}?", 15)

    assert fake_key not in json.dumps(plan.to_dict())
    assert fake_key not in caplog.text
