"""Tests for the config-driven provider layer (all offline via respx)."""

import httpx
import pytest
import respx
from pydantic import ValidationError

from src.core.config import settings
from src.providers.config import load_models_config
from src.providers.errors import (
    AuthError,
    BadResponse,
    ProviderDown,
    RateLimited,
    classify_exception,
    parse_retry_after,
)
from src.providers.gemini_provider import GeminiProvider
from src.providers.openai_compat import OpenAICompatibleProvider
from src.providers.quota import get_limiter
from src.providers.registry import ProviderDisabledError, get_provider
from src.providers.router import ModelRouter
from tests.conftest import make_models_yaml


@pytest.fixture(autouse=True)
def _fresh_quota_state() -> None:
    """generate() reports 429s into the shared limiter; reset per test."""
    get_limiter().reset()


def _custom_providers() -> dict:
    return {
        "groq": [
            {
                "id": "groq-custom-fast",
                "family": "gpt-oss",
                "roles": ["solver", "planner"],
            }
        ],
        "cerebras": [
            {
                "id": "cerebras-custom-strong",
                "family": "qwen",
                "roles": ["solver", "critic"],
            }
        ],
        "openrouter": [
            {
                "id": "or-custom-research",
                "family": "gemini",
                "roles": ["researcher", "planner"],
            }
        ],
    }


SUCCESS_BODY = {
    "id": "chatcmpl-test",
    "choices": [
        {
            "message": {"role": "assistant", "content": "hello"},
            "finish_reason": "stop",
        }
    ],
    "usage": {"prompt_tokens": 5, "completion_tokens": 7, "total_tokens": 12},
}


def _messages():
    from src.providers.base import ChatMessage

    return [ChatMessage(role="user", content="hi")]


def _provider(**kwargs):
    args = {
        "provider_id": "test",
        "api_key": "k",
        "base_url": "https://api.test/v1",
        "default_model": "m",
    }
    args.update(kwargs)
    return OpenAICompatibleProvider(**args)


# ── Catalog loading & validation ──────────────────────────────────────


def test_repo_catalog_loads_with_sane_entries() -> None:
    config = load_models_config()
    assert set(config.providers) >= {"gemini", "groq", "cerebras", "openrouter"}
    for provider_id, spec in config.providers.items():
        for model in spec.models:
            assert model.id and model.family and model.roles, provider_id


def test_unknown_family_fails_loudly(tmp_path) -> None:
    providers = _custom_providers()
    providers["groq"][0]["family"] = "skynet"
    with pytest.raises(ValidationError, match="unknown model family"):
        load_models_config(make_models_yaml(tmp_path, providers))


def test_missing_field_fails_loudly(tmp_path) -> None:
    providers = _custom_providers()
    del providers["groq"][0]["id"]
    with pytest.raises(ValidationError):
        load_models_config(make_models_yaml(tmp_path, providers))


def test_missing_file_fails_loudly(tmp_path) -> None:
    with pytest.raises(FileNotFoundError):
        load_models_config(tmp_path / "nope.yaml")


def test_legacy_provider_limits_rejected(tmp_path) -> None:
    """One shape only: provider-level `limits:` fails validation."""
    path = tmp_path / "models.yaml"
    path.write_text(
        "providers:\n"
        "  groq:\n"
        "    base: openai-compatible\n"
        "    url: http://127.0.0.1:9/v1\n"
        "    enabled: true\n"
        "    models:\n"
        "      - id: m\n"
        "        family: gpt-oss\n"
        "        roles: [solver]\n"
        "        scope: model\n"
        "        limits: {rpm: 1, rpd: 1, tpm: 1, context_tokens: 100}\n"
        "    limits: {rpm: 1, rpd: 1, tpm: 1}\n",
        encoding="utf-8",
    )
    with pytest.raises(ValidationError):
        load_models_config(path)


def test_unlimited_literal_accepted(tmp_path) -> None:
    providers = _custom_providers()
    providers["groq"][0]["limits"] = {"tpm": "unlimited"}
    config = load_models_config(make_models_yaml(tmp_path, providers))
    assert config.limits_of("groq", "groq-custom-fast").tpm == "unlimited"


def test_tpd_optional_forms_accepted(tmp_path) -> None:
    """tpd accepts int / "unlimited" / absent / null — none fail validation."""
    from src.providers.config import validate_limits_filled

    providers = _custom_providers()
    providers["groq"][0]["limits"] = {"tpd": 50000}
    providers["cerebras"][0]["limits"] = {"tpd": "unlimited"}
    providers["openrouter"][0]["limits"] = {"tpd": None}
    config = load_models_config(make_models_yaml(tmp_path, providers))
    assert config.limits_of("groq", "groq-custom-fast").tpd == 50000
    assert config.limits_of("cerebras", "cerebras-custom-strong").tpd == "unlimited"
    assert config.limits_of("openrouter", "or-custom-research").tpd is None
    validate_limits_filled(config)  # tpd never blocks enabled providers


def test_limit_scope_defaults_to_model(tmp_path) -> None:
    config = load_models_config(make_models_yaml(tmp_path, _custom_providers()))
    assert config.scope_of("groq", "groq-custom-fast") == "model"


def test_model_spec_unknown_ids_raise_key_error(tmp_path) -> None:
    config = load_models_config(make_models_yaml(tmp_path, _custom_providers()))
    with pytest.raises(KeyError):
        config.model_spec("nope", "groq-custom-fast")
    with pytest.raises(KeyError):
        config.model_spec("groq", "nope")


def test_validate_filled_passes_on_filled_catalog(tmp_path) -> None:
    from src.providers.config import validate_limits_filled

    validate_limits_filled(
        load_models_config(make_models_yaml(tmp_path, _custom_providers()))
    )


def test_validate_filled_ignores_disabled_providers(tmp_path) -> None:
    from src.providers.config import validate_limits_filled

    providers = _custom_providers()
    providers["groq"][0]["limits"] = {"rpm": None}
    validate_limits_filled(
        load_models_config(make_models_yaml(tmp_path, providers, enabled=False))
    )


def test_validate_filled_raises_on_enabled_nulls(tmp_path) -> None:
    from src.providers.config import LimitsNotFilledError, validate_limits_filled

    providers = _custom_providers()
    providers["groq"][0]["limits"] = {"rpm": None}
    with pytest.raises(LimitsNotFilledError, match="groq-custom-fast"):
        validate_limits_filled(
            load_models_config(make_models_yaml(tmp_path, providers))
        )


def test_repo_catalog_validation_flags_gemini() -> None:
    from src.providers.config import LimitsNotFilledError, validate_limits_filled

    with pytest.raises(LimitsNotFilledError, match="gemini-3.8-flash"):
        validate_limits_filled(load_models_config())


def test_provider_limits_issue_is_safe_and_actionable(tmp_path) -> None:
    from src.providers.config import provider_limits_issue

    providers = _custom_providers()
    providers["groq"][0]["limits"] = {"rpm": None, "rpd": None, "tpm": None}
    config = load_models_config(make_models_yaml(tmp_path, providers))
    issue = provider_limits_issue("groq", config.providers["groq"])
    assert issue is not None
    assert "groq-custom-fast" in issue
    assert "rpm" in issue and "rpd" in issue and "tpm" in issue
    assert "test-key" not in issue


def test_provider_limits_issue_is_none_when_filled_or_disabled(tmp_path) -> None:
    from src.providers.config import provider_limits_issue

    config = load_models_config(make_models_yaml(tmp_path, _custom_providers()))
    assert provider_limits_issue("groq", config.providers["groq"]) is None

    providers = _custom_providers()
    providers["groq"][0]["limits"] = {"rpm": None}
    disabled = load_models_config(
        make_models_yaml(tmp_path, providers, enabled=False, filename="disabled.yaml")
    )
    assert provider_limits_issue("groq", disabled.providers["groq"]) is None


def test_router_skips_provider_with_unfilled_limits(tmp_path, monkeypatch) -> None:
    from src.providers.config import LimitsNotFilledError, validate_provider_limits

    providers = _custom_providers()
    providers["groq"][0]["limits"] = {"rpm": None}
    config = load_models_config(make_models_yaml(tmp_path, providers))
    for pid in ("groq", "cerebras", "openrouter"):
        monkeypatch.setattr(settings, f"{pid}_api_key", "test-key")
    router = ModelRouter(config=config)
    assert "groq" not in router.get_available_providers()
    assert router.get_live_count() == 2
    with pytest.raises(LimitsNotFilledError, match="LIMITS NOT FILLED"):
        validate_provider_limits("groq", config.providers["groq"])


# ── Generic provider: success ─────────────────────────────────────────


@respx.mock
async def test_success_extracts_content_and_usage() -> None:
    route = respx.post("https://api.test/v1/chat/completions").mock(
        return_value=httpx.Response(200, json=SUCCESS_BODY)
    )
    response = await _provider().generate(_messages())

    assert route.called
    assert response.content == "hello"
    assert (response.input_tokens, response.output_tokens, response.total_tokens) == (
        5,
        7,
        12,
    )
    assert response.provider == "test" and response.model == "m"

    import json as jsonlib

    sent = jsonlib.loads(respx.calls[0].request.content.decode())
    assert sent["model"] == "m" and sent["messages"] == [
        {"role": "user", "content": "hi"}
    ]
    assert respx.calls[0].request.headers["authorization"] == "Bearer k"


# ── Generic provider: error taxonomy ──────────────────────────────────


@respx.mock
async def test_429_surfaces_immediately_for_router_failover() -> None:
    route = respx.post("https://api.test/v1/chat/completions").mock(
        side_effect=[
            httpx.Response(
                429,
                headers={"retry-after": "99999"},
                json={"error": {"message": "quota exhausted"}},
            ),
            httpx.Response(200, json=SUCCESS_BODY),
        ]
    )
    # Even with retries configured and a huge Retry-After, the adapter must
    # not sleep/retry the same rate-limited model. generate() reports cooldown.
    with pytest.raises(RateLimited) as exc_info:
        await _provider(max_retries=2).generate(_messages())
    assert exc_info.value.retry_after == 99999.0
    assert route.call_count == 1
    assert get_limiter().is_exhausted(
        "test", _provider()._fingerprint, "m"
    )


@respx.mock
async def test_persistent_429_raises_rate_limited_with_retry_after() -> None:
    respx.post("https://api.test/v1/chat/completions").mock(
        return_value=httpx.Response(429, headers={"retry-after": "3"})
    )
    with pytest.raises(RateLimited) as exc_info:
        await _provider(max_retries=0).generate(_messages())
    assert exc_info.value.retry_after == 3.0


@respx.mock
async def test_401_raises_auth_error_without_retry() -> None:
    route = respx.post("https://api.test/v1/chat/completions").mock(
        return_value=httpx.Response(401, json={"error": {"message": "bad key"}})
    )
    with pytest.raises(AuthError):
        await _provider(max_retries=2).generate(_messages())
    assert route.call_count == 1


@respx.mock
async def test_connection_error_raises_provider_down() -> None:
    respx.post("https://api.test/v1/chat/completions").mock(
        side_effect=httpx.ConnectError("boom")
    )
    with pytest.raises(ProviderDown):
        await _provider(max_retries=1).generate(_messages())
    assert len(respx.calls) == 2


@respx.mock
async def test_malformed_body_raises_bad_response() -> None:
    respx.post("https://api.test/v1/chat/completions").mock(
        return_value=httpx.Response(200, text="not json")
    )
    with pytest.raises(BadResponse):
        await _provider(max_retries=2).generate(_messages())


@respx.mock
async def test_missing_choices_raises_bad_response() -> None:
    respx.post("https://api.test/v1/chat/completions").mock(
        return_value=httpx.Response(200, json={"usage": {}})
    )
    with pytest.raises(BadResponse):
        await _provider().generate(_messages())


def test_retry_after_parsing() -> None:
    assert parse_retry_after("120") == 120.0
    assert parse_retry_after(None) is None
    assert parse_retry_after("garbage") is None


# ── Shared error classification (Gemini conformance) ──────────────────


class _StubStatusError(Exception):
    def __init__(self, status_code: int) -> None:
        super().__init__(f"HTTP {status_code}")
        self.status_code = status_code


def test_classify_exception_shapes() -> None:
    assert isinstance(classify_exception("p", _StubStatusError(429)), RateLimited)
    assert isinstance(classify_exception("p", _StubStatusError(401)), AuthError)
    assert isinstance(classify_exception("p", _StubStatusError(503)), ProviderDown)
    assert isinstance(classify_exception("p", TimeoutError("slow")), ProviderDown)
    original = RateLimited("p", "x", retry_after=1.0)
    assert classify_exception("p", original) is original
    assert isinstance(classify_exception("p", RuntimeError("weird")), ProviderDown)


# ── Registry ──────────────────────────────────────────────────────────


def test_registry_builds_generic_and_gemini() -> None:
    groq = get_provider("groq", "k")
    assert isinstance(groq, OpenAICompatibleProvider)
    assert groq.get_available_models()[0] == "openai/gpt-oss-20b"

    gemini = get_provider("gemini", "k")
    assert isinstance(gemini, GeminiProvider)
    assert gemini.default_model == "gemini-3.8-flash"


def test_registry_rejects_unknown_and_disabled() -> None:
    with pytest.raises(KeyError):
        get_provider("skynet", "k")
    with pytest.raises(ProviderDisabledError):
        get_provider("huggingface", "k")


# ── Switching a model id = editing only models.yaml ───────────────────


def test_model_ids_come_from_yaml_only(tmp_path, monkeypatch) -> None:
    path = make_models_yaml(tmp_path, _custom_providers())
    for pid in ("groq", "cerebras", "openrouter"):
        monkeypatch.setattr(settings, f"{pid}_api_key", "test-key")

    config = load_models_config(path)
    router = ModelRouter(config=config)
    assert router.get_live_count() == 3
    assert router.route("solver").model == "groq-custom-fast"

    path.write_text(
        path.read_text(encoding="utf-8").replace("groq-custom-fast", "groq-turbo"),
        encoding="utf-8",
    )
    router2 = ModelRouter(config=load_models_config(path))
    assert router2.route("solver").model == "groq-turbo"
    assert router2.route("solver").family == "gpt-oss"


def test_repo_router_uses_catalog_ids() -> None:
    config = load_models_config()
    known = {m.id for spec in config.providers.values() for m in spec.models}
    # Live providers come from the real .env; every routed id must be catalogued.
    router = ModelRouter(config=config)
    for role in ("solver", "researcher", "critic", "synthesizer", "planner"):
        try:
            assignment = router.route(role)
        except RuntimeError:
            pytest.skip("fewer than 3 live providers in this environment")
        assert assignment.model in known
