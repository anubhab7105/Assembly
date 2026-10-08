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
from src.providers.registry import ProviderDisabledError, get_provider
from src.providers.router import ModelRouter

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

CUSTOM_YAML = """
providers:
  groq:
    base: openai-compatible
    url: http://127.0.0.1:9/v1
    enabled: true
    models:
      - {id: groq-custom-fast, family: gpt-oss, roles: [solver, planner], context_tokens: null}
    limits: {rpm: null, rpd: null, tpm: null}
  cerebras:
    base: openai-compatible
    url: http://127.0.0.1:9/v1
    enabled: true
    models:
      - {id: cerebras-custom-strong, family: qwen, roles: [solver, critic], context_tokens: null}
    limits: {rpm: null, rpd: null, tpm: null}
  openrouter:
    base: openai-compatible
    url: http://127.0.0.1:9/v1
    enabled: true
    models:
      - {id: or-custom-research, family: gemini, roles: [researcher, planner], context_tokens: null}
    limits: {rpm: null, rpd: null, tpm: null}
"""


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
    path = tmp_path / "models.yaml"
    path.write_text(
        CUSTOM_YAML.replace("family: gpt-oss", "family: skynet"), encoding="utf-8"
    )
    with pytest.raises(ValidationError, match="unknown model family"):
        load_models_config(path)


def test_missing_field_fails_loudly(tmp_path) -> None:
    path = tmp_path / "models.yaml"
    path.write_text(
        CUSTOM_YAML.replace("- {id: groq-custom-fast,", "- {"), encoding="utf-8"
    )
    with pytest.raises(ValidationError):
        load_models_config(path)


def test_missing_file_fails_loudly(tmp_path) -> None:
    with pytest.raises(FileNotFoundError):
        load_models_config(tmp_path / "nope.yaml")


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
async def test_429_retries_with_retry_after_then_succeeds() -> None:
    respx.post("https://api.test/v1/chat/completions").mock(
        side_effect=[
            httpx.Response(
                429, headers={"retry-after": "0"}, json={"error": {"message": "slow"}}
            ),
            httpx.Response(200, json=SUCCESS_BODY),
        ]
    )
    response = await _provider(max_retries=1).generate(_messages())
    assert response.content == "hello"
    assert len(respx.calls) == 2


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
    path = tmp_path / "models.yaml"
    path.write_text(CUSTOM_YAML, encoding="utf-8")
    for pid in ("groq", "cerebras", "openrouter"):
        monkeypatch.setattr(settings, f"{pid}_api_key", "test-key")

    config = load_models_config(path)
    router = ModelRouter(config=config)
    assert router.get_live_count() == 3
    assert router.route("solver").model == "groq-custom-fast"

    path.write_text(
        CUSTOM_YAML.replace("groq-custom-fast", "groq-turbo"), encoding="utf-8"
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
