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

    status, ids, body, metadata = await keys_mod._list_gemini(fake_key)

    assert status == 200
    assert ids == ["gemini-3.8-flash"]
    assert body == ""
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

    status, ids, body, metadata, quota_headers = await keys_mod._list_openai(
        "https://api.groq.com/openai/v1",
        fake_key,
        {},
    )

    assert status == 200
    assert ids == ["openai/gpt-oss-20b"]
    assert body == ""
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

    assert result == {"free_model_requests_per_day": 50}
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
    assert await keys_mod._openrouter_key_info(fake_key) == {}


def test_huggingface_verification_preserves_unknown_unprobed_models() -> None:
    from src.providers.config import ProviderSpec

    spec = ProviderSpec.model_validate({
        "base": "huggingface",
        "enabled": False,
        "models": [
            {"id": "org/model-a", "family": "llama", "roles": ["solver"]},
            {"id": "org/model-b", "family": "llama", "roles": ["critic"]},
        ],
    })
    verification = keys_mod._build_key_metadata_verification(
        "huggingface", spec, ["org/model-a"], {}, {}, {},
        model_availability={"org/model-a": True, "org/model-b": None},
    )
    assert [model.available for model in verification.models] == [True, None]
