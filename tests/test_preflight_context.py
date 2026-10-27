"""Group 1 backend tests: shared request context + POST /api/preflight.

All offline: fake keys only ever reach ModelRouter construction (no
network), endpoint tests stub the builder. Canary strings must appear in
no response or log.
"""

import logging

import pytest
from fastapi.testclient import TestClient

CANARY_PROV = "gsk-CANARY-CTX-D4E5F6"
CANARY_SEARCH = "tvly-CANARY-CTX-A1B2C3"
CANARY_Q = "Canary context question ZULU-78: why do hummingbirds hum?"


def _ctx(**over):
    from src.api.request_context import build_request_context

    args = {
        "provider_keys": {},
        "search_keys": None,
        "selected": [],
        "pins": {},
        "usage_snapshot": [],
    }
    args.update(over)
    # Keep tests independent of production models.yaml freshness. Offline
    # tests use a temporary, explicit synthetic catalog for provider keys.
    from pathlib import Path
    import tempfile
    from unittest.mock import patch

    from tests.conftest import make_models_yaml

    with tempfile.TemporaryDirectory() as tmp:
        path = make_models_yaml(
            Path(tmp),
            {
                "groq": [
                    {
                        "id": "openai/gpt-oss-20b",
                        "family": "gpt-oss",
                        "roles": ["solver", "critic", "planner"],
                    }
                ],
                "openrouter": [
                    {
                        "id": "google/gemma-4-26b-a4b-it:free",
                        "family": "gemma",
                        "roles": ["solver", "critic", "planner"],
                    }
                ],
                "cerebras": [
                    {
                        "id": "gpt-oss-120b",
                        "family": "qwen",
                        "roles": ["solver", "critic", "planner"],
                    }
                ],
            },
        )
        with patch("src.providers.config.default_catalog_path", return_value=path):
            return build_request_context(
                args["provider_keys"],
                args["search_keys"],
                args["selected"],
                args["pins"],
                args["usage_snapshot"],
            )


def test_builder_empty_keys_is_blocked() -> None:
    from src.api.request_context import _diversity_is_blocked

    ctx = _ctx()
    assert ctx.allowed == set()
    assert ctx.pins == {}
    assert ctx.has_search_key is False
    assert _diversity_is_blocked(ctx.router, ctx.allowed) is True


def test_builder_fake_keys_offline() -> None:
    from src.api.request_context import _diversity_is_blocked

    ctx = _ctx(provider_keys={"groq": CANARY_PROV})
    assert _diversity_is_blocked(ctx.router, ctx.allowed) is False
    assert isinstance(ctx.quota_snapshot, list)


def test_builder_selection_and_search_flag() -> None:
    ctx = _ctx(
        provider_keys={"groq": CANARY_PROV},
        search_keys={"tavily": CANARY_SEARCH},
        selected=["openai/gpt-oss-20b", "no-such-model"],
        pins={"solver": "openai/gpt-oss-20b"},
    )
    assert ctx.allowed == {"openai/gpt-oss-20b"}
    assert ctx.pins == {"solver": "openai/gpt-oss-20b"}
    assert ctx.has_search_key is True


def test_builder_empty_search_value_means_keyless() -> None:
    ctx = _ctx(search_keys={"tavily": ""})
    assert ctx.has_search_key is False


def test_cross_provider_pin_uses_matching_provider_adapter() -> None:
    ctx = _ctx(
        provider_keys={"groq": CANARY_PROV, "cerebras": "csk-TEST-KEY-123"},
        pins={"critic": "gpt-oss-120b"},
    )

    decision = ctx.router.route("critic")

    assert decision.model == "gpt-oss-120b"
    assert decision.provider_name == "cerebras"
    assert decision.provider is ctx.router._w._providers["cerebras"]
    assert ctx.router.fallback_for(decision, RuntimeError("simulated provider failure")) is None


def test_pin_without_provider_key_fails_clearly() -> None:
    from src.providers.router import PinViolationError

    with pytest.raises(PinViolationError, match="not configured or available"):
        _ctx(
            provider_keys={"groq": CANARY_PROV},
            pins={"critic": "gpt-oss-120b"},
        )


def test_pin_excluded_by_model_selection_is_rejected() -> None:
    from src.providers.router import PinViolationError

    with pytest.raises(PinViolationError, match="excluded by the current model selection"):
        _ctx(
            provider_keys={"groq": CANARY_PROV, "cerebras": "csk-TEST-KEY-123"},
            selected=["openai/gpt-oss-20b"],
            pins={"critic": "gpt-oss-120b"},
        )


def test_critic_pin_sharing_solver_family_is_rejected() -> None:
    from src.providers.router import PinViolationError

    ctx = _ctx(
        provider_keys={"groq": CANARY_PROV, "openrouter": "sk-TEST-KEY-456"},
        pins={
            "solver": "openai/gpt-oss-20b",
            "critic": "openai/gpt-oss-20b",
        },
    )

    with pytest.raises(PinViolationError, match="critic in a solver's family"):
        ctx.router.route_team(
            [
                {"agent_type": "solver", "role_description": "Solve the problem"},
                {"agent_type": "critic", "role_description": "Review the solution"},
            ]
        )


def test_unpinned_routing_keeps_router_choice() -> None:
    ctx = _ctx(provider_keys={"groq": CANARY_PROV, "cerebras": "csk-TEST-KEY-123"})

    decision = ctx.router.route("critic")

    assert decision.provider_name == "groq"
    assert decision.model == "openai/gpt-oss-20b"


def test_preflight_uses_request_keys(monkeypatch) -> None:
    from types import SimpleNamespace

    import src.api.preflight as preflight_mod
    from src.api.request_context import RequestContext
    from src.main import app

    seen: dict = {}

    def _fake(*args, **kwargs):
        seen["provider_keys"] = args[0] if args else kwargs.get("provider_keys")
        seen["search_keys"] = args[1] if len(args) > 1 else kwargs.get("search_keys")
        return RequestContext(
            router=SimpleNamespace(
                quota_snapshot=lambda: [
                    {
                        "provider": "p",
                        "rpm_limit": 30,
                        "rpd_remaining": 1000,
                        "tpm_limit": None,
                        "tpd_remaining": None,
                        "cooldown_seconds": 0.0,
                        "scope": "model",
                        "model": "m",
                    }
                ],
                available_families=lambda: ["gemini", "qwen", "gpt-oss"],
            ),
            allowed=set(),
            pins={},
            quota_snapshot=[],
            has_search_key=True,
        )

    monkeypatch.setattr(preflight_mod, "build_request_context", _fake)
    client = TestClient(app)
    res = client.post(
        "/api/preflight",
        json={
            "question": CANARY_Q,
            "time_budget_minutes": 5,
            "provider_keys": {"groq": CANARY_PROV},
            "search_keys": {"tavily": CANARY_SEARCH},
            "model_selection": {"selected": [], "pins": {}},
            "usage_snapshot": [],
        },
    )
    assert res.status_code == 200, res.text
    assert res.json()["feasible"] is True
    assert seen.get("provider_keys") == {"groq": CANARY_PROV}
    assert seen.get("search_keys") == {"tavily": CANARY_SEARCH}
    assert CANARY_PROV not in res.text
    assert CANARY_SEARCH not in res.text


def test_preflight_canary_never_in_422(caplog) -> None:
    from src.main import app

    client = TestClient(app)
    with caplog.at_level(logging.INFO, logger="assembly"):
        res = client.post(
            "/api/preflight",
            json={
                "question": "",
                "time_budget_minutes": 3,
                "provider_keys": {"groq": CANARY_PROV},
                "search_keys": {"tavily": CANARY_SEARCH},
            },
        )
    assert res.status_code == 422
    assert CANARY_PROV not in res.text
    assert CANARY_SEARCH not in res.text
    assert CANARY_PROV not in caplog.text
    assert CANARY_SEARCH not in caplog.text
