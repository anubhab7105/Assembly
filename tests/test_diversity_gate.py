"""Family-based diversity gate tests (PRD FR-10, D3).

The gate counts DISTINCT usable families (enabled + key + limits filled +
not cooled-down/exhausted + inside selection). Same family twice = once.
"""

from src.providers.config import load_models_config
from src.providers.quota import QuotaLimiter, fingerprint_key
from src.providers.router import FAMILY_GATE_THRESHOLDS, ModelRouter
from tests.conftest import make_models_yaml

ALL = ["solver", "critic", "researcher", "synthesizer", "planner"]


def _router(tmp_path, providers, keys, **kwargs):
    path = make_models_yaml(tmp_path, providers)
    config = load_models_config(path)
    limiter = QuotaLimiter(config=config, **kwargs)
    return ModelRouter(config=config, keys=keys, limiter=limiter), limiter, config


def _groq_openrouter():
    return {
        "groq": [
            {"id": "gpt-20b", "family": "gpt-oss", "roles": list(ALL)},
            {"id": "qwen-27b", "family": "qwen", "roles": list(ALL)},
        ],
        "openrouter": [
            {"id": "gemma-26b", "family": "gemma", "roles": list(ALL)},
            {"id": "nemotron-120b", "family": "nemotron", "roles": list(ALL)},
        ],
    }


def test_thresholds_live_in_one_constant() -> None:
    assert FAMILY_GATE_THRESHOLDS == {"ok": 3, "warn": 2}


def test_groq_plus_openrouter_is_four_families_ok(tmp_path) -> None:
    router, _, _ = _router(
        tmp_path, _groq_openrouter(), {"groq": "k1", "openrouter": "k2"}
    )
    gate = router.diversity_gate()
    assert gate.level == "OK"
    assert gate.families_count == 4
    assert set(gate.families_ready) == {"gpt-oss", "qwen", "gemma", "nemotron"}
    assert gate.providers_count == 2
    assert gate.to_dict()["level"] == "OK"


def test_two_providers_same_family_is_degraded(tmp_path) -> None:
    providers = {
        "pa": [{"id": "pa-m", "family": "llama", "roles": list(ALL)}],
        "pb": [{"id": "pb-m", "family": "llama", "roles": list(ALL)}],
    }
    router, _, _ = _router(tmp_path, providers, {"pa": "k1", "pb": "k2"})
    gate = router.diversity_gate()
    assert gate.level == "DEGRADED"
    assert gate.families_ready == ["llama"]
    assert gate.providers_count == 2  # two providers, one family
    assert any("lower-confidence" in r for r in gate.reasons)


def test_two_families_is_warn_with_fix_hint(tmp_path) -> None:
    providers = {
        "pa": [{"id": "pa-m", "family": "gpt-oss", "roles": list(ALL)}],
        "pb": [{"id": "pb-m", "family": "qwen", "roles": list(ALL)}],
    }
    router, _, _ = _router(tmp_path, providers, {"pa": "k1", "pb": "k2"})
    gate = router.diversity_gate()
    assert gate.level == "WARN"
    assert gate.families_count == 2
    assert any("to reach 3 families" in r for r in gate.reasons)


def test_zero_families_is_blocked(tmp_path) -> None:
    providers = {
        "pa": [{"id": "pa-m", "family": "gpt-oss", "roles": list(ALL)}],
    }
    router, _, _ = _router(tmp_path, providers, {})
    gate = router.diversity_gate()
    assert gate.level == "BLOCKED"
    assert gate.families_count == 0


def test_selection_narrowing_to_two_families_is_warn(tmp_path) -> None:
    router, _, _ = _router(
        tmp_path, _groq_openrouter(), {"groq": "k1", "openrouter": "k2"}
    )
    gate = router.diversity_gate({"gpt-20b", "qwen-27b"})
    assert gate.level == "WARN"
    assert set(gate.families_ready) == {"gpt-oss", "qwen"}


def test_cooled_down_provider_is_excluded(tmp_path) -> None:
    router, limiter, _ = _router(
        tmp_path, _groq_openrouter(), {"groq": "k1", "openrouter": "k2"}
    )
    fp = fingerprint_key("k1")
    limiter.report_429("groq", fp, "gpt-20b", retry_after=120)
    limiter.report_429("groq", fp, "qwen-27b", retry_after=120)
    gate = router.diversity_gate()
    assert set(gate.families_ready) == {"gemma", "nemotron"}
    assert gate.level == "WARN"


def test_exhausted_daily_quota_is_excluded(tmp_path) -> None:
    router, limiter, _ = _router(
        tmp_path, _groq_openrouter(), {"groq": "k1", "openrouter": "k2"}
    )
    limiter.set_usage_snapshot(
        [
            {"provider": "groq", "model": "gpt-20b", "count": 1000, "tokens": 0},
            {"provider": "groq", "model": "qwen-27b", "count": 1000, "tokens": 0},
        ],
        owner_key_ids={"groq": fingerprint_key("k1")},
    )
    gate = router.diversity_gate()
    assert "gpt-oss" not in gate.families_ready
    assert "qwen" not in gate.families_ready
    assert gate.level == "WARN"


def test_unfilled_limits_exclude_the_provider(tmp_path) -> None:
    providers = _groq_openrouter()
    providers["groq"][0]["limits"] = {"rpm": None}
    path = make_models_yaml(tmp_path, providers)
    config = load_models_config(path)
    router = ModelRouter(config=config, keys={"groq": "k1", "openrouter": "k2"})
    assert "groq" not in router.get_available_providers()
    gate = router.diversity_gate()
    assert "gpt-oss" not in gate.families_ready or "qwen" not in gate.families_ready


def test_enforce_minimum_blocks_only_on_zero(tmp_path) -> None:
    import pytest

    providers = {
        "pa": [{"id": "pa-m", "family": "llama", "roles": list(ALL)}],
    }
    router, _, _ = _router(tmp_path, providers, {"pa": "k1"})
    # 1 family used to raise under the provider-count gate; now it runs.
    router._enforce_minimum()
    empty, _, _ = _router(tmp_path, providers, {})
    with pytest.raises(RuntimeError, match="usable model family"):
        empty._enforce_minimum()


def test_status_preflight_carry_diversity(monkeypatch) -> None:
    from fastapi.testclient import TestClient

    from src.main import app

    client = TestClient(app)
    res = client.get("/api/providers/status")
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["diversity"]["level"] in ("OK", "WARN", "DEGRADED", "BLOCKED")
    assert "families_ready" in body["diversity"]

    pre = client.post(
        "/api/preflight",
        json={
            "question": "Is 2+2 4?",
            "time_budget_minutes": 3,
            "provider_keys": {},
            "model_selection": {"selected": [], "pins": {}},
            "usage_snapshot": [],
        },
    )
    assert pre.status_code == 200, pre.text
    assert pre.json()["diversity"]["level"] in ("OK", "WARN", "DEGRADED", "BLOCKED")


def test_single_family_run_labels_lower_confidence() -> None:
    """DEGRADED routing caps a High consensus at Moderate in the event."""
    from src.orchestration.orchestrator import cap_label_for_degraded

    assert cap_label_for_degraded("High", True) == "Moderate"
    assert cap_label_for_degraded("Moderate", True) == "Moderate"
    assert cap_label_for_degraded("Low", True) == "Low"
    assert cap_label_for_degraded("High", False) == "High"
