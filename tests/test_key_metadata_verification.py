"""Automatic provider metadata verification tests (offline, no key leakage)."""

import httpx
import pytest
import respx

import src.api.keys as keys_mod


@pytest.mark.asyncio
@respx.mock
async def test_gemini_catalog_extracts_only_documented_model_token_limits(fake_key: str) -> None:
    respx.get(keys_mod._GEMINI_LIST_URL).mock(
        return_value=httpx.Response(
            200,
            json={
                "models": [
                    {
                        "name": "models/gemini-3.8-flash",
                        "inputTokenLimit": 1_000_000,
                        "outputTokenLimit": 64_000,
                    }
                ]
            },
        )
    )

    status, ids, invalid_key_signal, metadata = await keys_mod._list_gemini(fake_key)

    assert status == 200
    assert ids == ["gemini-3.8-flash"]
    assert invalid_key_signal is False
    assert metadata == {
        "gemini-3.8-flash": {
            "context_tokens": 1_000_000,
            "output_tokens": 64_000,
        }
    }
    assert fake_key not in repr(metadata)


@pytest.mark.asyncio
@respx.mock
async def test_groq_models_probe_keeps_only_limit_headers_with_known_meanings(
    fake_key: str,
) -> None:
    route = respx.get("https://api.groq.com/openai/v1/models").mock(
        return_value=httpx.Response(
            200,
            headers={
                "x-ratelimit-limit-requests": "14400",
                "x-ratelimit-limit-tokens": "18000",
                "x-ratelimit-remaining-requests": "14000",
                "x-ratelimit-reset-requests": "2m",
                "retry-after": "3",
                "authorization": "Bearer should-not-be-forwarded",
            },
            json={
                "data": [
                    {
                        "id": "openai/gpt-oss-20b",
                        "context_window": 131072,
                    }
                ]
            },
        )
    )

    status, ids, invalid_key_signal, metadata, quota_headers = await keys_mod._list_openai(
        "https://api.groq.com/openai/v1",
        fake_key,
        {},
    )

    assert status == 200
    assert ids == ["openai/gpt-oss-20b"]
    assert invalid_key_signal is False
    assert metadata == {"openai/gpt-oss-20b": {"context_tokens": 131072}}
    assert quota_headers == {
        "x-ratelimit-limit-requests": "14400",
        "x-ratelimit-limit-tokens": "18000",
    }
    assert route.calls[0].request.headers["Authorization"] == f"Bearer {fake_key}"
    assert fake_key not in repr((metadata, quota_headers))


@pytest.mark.asyncio
@respx.mock
async def test_openrouter_key_info_reports_free_model_allowance_not_credit_budget(
    fake_key: str,
) -> None:
    route = respx.get("https://openrouter.ai/api/v1/key").mock(
        return_value=httpx.Response(
            200,
            json={
                "data": {
                    "limit": 100,
                    "limit_remaining": 74,
                    "free_model_daily_requests": {
                        "used": 10,
                        "limit": 50,
                        "remaining": 40,
                    },
                    "rate_limit": {"interval": "1h", "requests": 1000},
                }
            },
        )
    )

    result = await keys_mod._openrouter_key_info(fake_key)

    status_code, metadata = result
    assert status_code == 200
    assert metadata == {"free_model_requests_per_day": 50}
    assert route.calls[0].request.headers["Authorization"] == f"Bearer {fake_key}"
    assert fake_key not in repr(result)


def test_quota_parser_rejects_non_integer_and_non_positive_values() -> None:
    assert keys_mod._positive_int("14400") == 14400
    assert keys_mod._positive_int(8000) == 8000
    assert keys_mod._positive_int("unlimited") is None
    assert keys_mod._positive_int(1.5) is None
    assert keys_mod._positive_int(True) is None
    assert keys_mod._positive_int("0") is None
    assert keys_mod._positive_int("-1") is None


@pytest.mark.asyncio
@respx.mock
async def test_openrouter_invalid_unicode_digit_limit_stays_unverified(fake_key: str) -> None:
    respx.get("https://openrouter.ai/api/v1/key").mock(
        return_value=httpx.Response(
            200, json={"data": {"free_model_daily_requests": {"limit": "²"}}}
        )
    )
    status_code, metadata = await keys_mod._openrouter_key_info(fake_key)
    assert status_code == 200
    assert metadata == {}


@pytest.mark.asyncio
@respx.mock
async def test_huggingface_key_test_probes_each_configured_model(
    monkeypatch: pytest.MonkeyPatch, fake_key: str
) -> None:
    from src.providers.config import ProviderSpec

    spec = ProviderSpec.model_validate({
        "base": "huggingface",
        "enabled": False,
        "models": [
            {"id": "org/model-a", "family": "llama", "roles": ["solver"]},
            {"id": "org/model-b", "family": "llama", "roles": ["critic"]},
        ],
    })
    monkeypatch.setattr(
        keys_mod, "load_models_config",
        lambda: type("Catalog", (), {"providers": {"huggingface": spec}})(),
    )
    respx.get(keys_mod._HF_MODEL_URL.format(model="org/model-a")).mock(return_value=httpx.Response(200))
    respx.get(keys_mod._HF_MODEL_URL.format(model="org/model-b")).mock(return_value=httpx.Response(404))

    response = await keys_mod.test_key(
        keys_mod.KeyTestRequest(provider="huggingface", key=fake_key),
        type("Request", (), {"client": type("Client", (), {"host": "127.0.0.1"})()})(),
    )

    assert response.valid is True
    assert response.verification is not None
    assert [(model.id, model.available) for model in response.verification.models] == [
        ("org/model-a", True),
        ("org/model-b", False),
    ]
    assert response.available_models == ["org/model-a"]
