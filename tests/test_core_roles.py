"""FR-2: every plan has a Solver and a Critic (offline)."""

from fastapi.testclient import TestClient

from src.api.events import ProgressEventType
from src.main import app
from src.orchestration.core_roles import (
    ensure_core_roles,
    final_roles_with_synthesizer,
    single_family_warning,
)
from src.orchestration.orchestrator import cap_label_for_degraded


def test_no_critic_gets_one() -> None:
    roles, adjustments = ensure_core_roles(["solver", "solver"], 4)
    assert "critic" in roles
    assert any("critic" in a for a in adjustments)


def test_no_solver_gets_one() -> None:
    roles, adjustments = ensure_core_roles(["critic", "researcher"], 4)
    assert "solver" in roles
    assert any("solver" in a for a in adjustments)


def test_over_cap_drops_researcher_first() -> None:
    roles, adjustments = ensure_core_roles(
        ["solver", "solver", "researcher", "critic"], 3
    )
    assert len(roles) == 3
    assert "researcher" not in roles
    assert "solver" in roles and "critic" in roles
    assert any("researcher" in a for a in adjustments)


def test_three_minute_tier_keeps_solver_critic_synthesizer() -> None:
    roles, _ = ensure_core_roles(["solver", "researcher", "critic"], 3)
    assert "solver" in roles and "critic" in roles
    final = final_roles_with_synthesizer(roles)
    assert "synthesizer" in final


def test_never_drops_last_solver_or_critic() -> None:
    roles, _ = ensure_core_roles(["solver", "critic"], 2)
    assert roles.count("solver") == 1 and roles.count("critic") == 1
    # Even an absurd cap keeps the pair (cap yields, guarantee wins).
    roles, _ = ensure_core_roles(["solver", "critic", "researcher"], 1)
    assert "solver" in roles and "critic" in roles


def test_preflight_shows_final_roles() -> None:
    client = TestClient(app)
    resp = client.post(
        "/api/preflight",
        json={"question": "What is 2+2?", "time_budget_minutes": 3},
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert "final_roles" in data
    assert "solver" in data["final_roles"]
    assert "critic" in data["final_roles"]
    assert "synthesizer" in data["final_roles"]


def test_old_preflight_routes_are_gone() -> None:
    client = TestClient(app)
    for method in ("get", "post"):
        resp = getattr(client, method)(
            "/api/executions/preflight",
            **({"params": {"question": "Hi?", "time_budget_minutes": 3}} if method == "get" else {"json": {"question": "Hi?", "time_budget_minutes": 3}}),
        )
        assert resp.status_code == 410, resp.text
        assert resp.json()["use"] == "POST /api/preflight"


def test_single_family_warns_and_lowers_confidence() -> None:
    warning = single_family_warning(["gemini"])
    assert warning is not None
    assert "Only one model family" in warning
    assert single_family_warning(["gemini", "qwen"]) is None
    assert cap_label_for_degraded("High", True) == "Moderate"
    assert cap_label_for_degraded("High", False) == "High"


def test_plan_adjusted_event_contract() -> None:
    from src.api.events import PAYLOAD_MODELS

    model = PAYLOAD_MODELS[ProgressEventType.PLAN_ADJUSTED]
    payload = model.model_validate(
        {
            "reason": "added critic",
            "added": ["added critic"],
            "removed": [],
            "final_roles": ["solver", "critic", "synthesizer"],
        }
    )
    assert payload.model_dump()["reason"] == "added critic"


async def test_orchestrator_emits_plan_adjusted(orchestrator) -> None:
    from src.providers.mock_provider import MockProvider

    events: list[dict] = []

    async def on_progress(event: dict) -> None:
        events.append(event)

    # Force a plan missing a critic via the mock planner script.
    for provider in orchestrator.router._providers.values():
        if isinstance(provider, MockProvider):
            provider._scripts["plan"] = {
                "problem_type": "general",
                "complexity": "low",
                "needs_research": False,
                "needs_code_execution": False,
                "suggested_roles": ["solver", "solver"],
                "estimated_rounds": 1,
            }
    result = await orchestrator.execute(
        execution_id="fr2-plan-adjusted",
        question="Short question?",
        time_budget_minutes=3,
        on_progress=on_progress,
    )
    assert result.status == "completed"
    kinds = {e["event_type"] for e in events}
    assert "plan.adjusted" in kinds
