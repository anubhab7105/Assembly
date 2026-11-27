"""Gemini key-Test classification (mocked list probe, offline).

Only an authentication failure may report "invalid". Quota, model
availability, and transport problems each report their own state, and
pasted-key whitespace never turns a valid key invalid.
"""

import logging

import httpx
import pytest
import respx
from pytest import LogCaptureFixture

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

import src.api.keys as keys_mod
from src.core.keystore import clean_key
from src.database.base import Base, get_db
from src.providers.errors import AuthError, TruncatedResponse
from src.providers.gemini_provider import _extract_text_and_finish

CANARY = "SECRET_CANARY_12345"


def _client(monkeypatch) -> TestClient:
    import src.api.executions as exec_mod
    from src.core.config import settings as _settings
    from src.main import app

    monkeypatch.setattr(_settings, "app_mode", "dev")
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
    return TestClient(app)


def _stub_list(
    monkeypatch: pytest.MonkeyPatch,
    status: int | None,
    ids: list[str],
    invalid_key_signal: bool = False,
    metadata: dict[str, dict[str, int]] | None = None,
) -> None:
    async def _fake(
        key: str,
    ) -> tuple[int | None, list[str], bool, dict[str, dict[str, int]]]:
        return status, ids, invalid_key_signal, metadata or {}

    monkeypatch.setattr(keys_mod, "_list_gemini", _fake)


def test_list_200_is_valid(monkeypatch, fake_key: str) -> None:
    _stub_list(
        monkeypatch,
        200,
        ["gemini-3.8-flash"],
        metadata={"gemini-3.8-flash": {"context_tokens": 1_000_000, "output_tokens": 64_000}},
    )
    res = _client(monkeypatch).post(
        "/api/keys/test", json={"provider": "gemini", "key": fake_key}
    )
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["valid"] is True
    assert body["rate_limited"] is False
    assert body["error_code"] is None
    assert body["model_available"] is True
    assert body["verification"]["models"][0]["context_tokens"] == 1_000_000
    assert body["verification"]["provider_enabled"] is True
    assert body["verification"]["quota_metadata_ready"] is False
    assert fake_key not in res.text


def test_list_200_missing_model_is_key_valid_with_alternatives(
    monkeypatch: pytest.MonkeyPatch, fake_key: str
) -> None:
    _stub_list(monkeypatch, 200, ["gemini-2.0-flash", "gemini-1.5-flash"])
    body = (
        _client(monkeypatch)
        .post("/api/keys/test", json={"provider": "gemini", "key": fake_key})
        .json()
    )
    assert body["valid"] is True
    assert body["error_code"] == "model_not_found"
    assert body["model_available"] is False
    assert "gemini-2.0-flash" in (body["available_models"] or [])
    assert "not available" in (body["message"] or "")


def test_list_400_api_key_invalid_is_invalid(monkeypatch, fake_key: str) -> None:
    _stub_list(
        monkeypatch,
        400,
        [],
        invalid_key_signal=True,
    )
    body = (
        _client(monkeypatch)
        .post("/api/keys/test", json={"provider": "gemini", "key": fake_key})
        .json()
    )
    assert body["valid"] is False
    assert body["error_code"] == "auth_error"


def test_list_401_is_invalid(monkeypatch, fake_key: str) -> None:
    _stub_list(monkeypatch, 401, [])
    body = (
        _client(monkeypatch)
        .post("/api/keys/test", json={"provider": "gemini", "key": fake_key})
        .json()
    )
    assert body["valid"] is False
    assert body["error_code"] == "auth_error"


def test_list_403_is_invalid(monkeypatch, fake_key: str) -> None:
    _stub_list(monkeypatch, 403, [])
    body = (
        _client(monkeypatch)
        .post("/api/keys/test", json={"provider": "gemini", "key": fake_key})
        .json()
    )
    assert body["valid"] is False
    assert body["error_code"] == "auth_error"


def test_list_429_is_quota_not_invalid(monkeypatch, fake_key: str) -> None:
    _stub_list(monkeypatch, 429, [])
    body = (
        _client(monkeypatch)
        .post("/api/keys/test", json={"provider": "gemini", "key": fake_key})
        .json()
    )
    assert body["rate_limited"] is True
    assert body["error_code"] == "rate_limited"
    assert "quota or rate limit" in (body["message"] or "")


def test_list_404_model_is_key_valid(monkeypatch, fake_key: str) -> None:
    _stub_list(monkeypatch, 404, [])
    body = (
        _client(monkeypatch)
        .post("/api/keys/test", json={"provider": "gemini", "key": fake_key})
        .json()
    )
    assert body["valid"] is True
    assert body["error_code"] == "model_not_found"
    assert body["model_available"] is False


def test_list_timeout_is_unreachable_never_invalid(monkeypatch, fake_key: str) -> None:
    _stub_list(monkeypatch, None, [])
    body = (
        _client(monkeypatch)
        .post("/api/keys/test", json={"provider": "gemini", "key": fake_key})
        .json()
    )
    assert body["valid"] is False
    assert body["error_code"] == "unreachable"
    assert "reach" in (body["message"] or "")


def test_trailing_newline_key_is_trimmed_before_probe(monkeypatch: pytest.MonkeyPatch) -> None:
    seen: dict[str, str] = {}

    async def _capture(
        key: str,
    ) -> tuple[int, list[str], bool, dict[str, dict[str, int]]]:
        seen["key"] = key
        return 200, ["gemini-3.8-flash"], False, {}

    monkeypatch.setattr(keys_mod, "_list_gemini", _capture)
    body = (
        _client(monkeypatch)
        .post("/api/keys/test", json={"provider": "gemini", "key": "pasteddkey123\n"})
        .json()
    )
    assert body["valid"] is True
    assert seen["key"] == "pasteddkey123"


def test_clean_key_strips_whitespace_and_zero_width() -> None:
    assert clean_key("  abc123  \n") == "abc123"
    assert clean_key("abc123\u200b\ufeff") == "abc123"
    assert clean_key("  \n ") == ""


def test_max_tokens_empty_generation_is_distinct_non_auth_error() -> None:
    """SDK 200 with MAX_TOKENS and no parts: key valid, turn empty."""

    class _Part:
        text = ""

    class _Content:
        parts: object = []  # type: ignore[assignment]

    class _Candidate:
        finish_reason = 2
        content = _Content()

    class _Response:
        candidates = [_Candidate()]  # noqa: RUF012

    text, finish = _extract_text_and_finish(_Response())
    assert text == ""
    assert finish == "MAX_TOKENS"
    err = TruncatedResponse("gemini", "empty generation (finish=MAX_TOKENS)")
    assert not isinstance(err, AuthError)


def test_canary_never_in_test_response_or_logs(monkeypatch: pytest.MonkeyPatch, caplog: LogCaptureFixture) -> None:
    _stub_list(monkeypatch, 401, [])
    with caplog.at_level(logging.INFO, logger="assembly"):
        res = _client(monkeypatch).post(
            "/api/keys/test", json={"provider": "gemini", "key": CANARY}
        )
    assert res.status_code == 200
    assert CANARY not in res.text
    assert CANARY not in caplog.text


def test_gemini_verification_reports_catalog_context_but_not_project_quotas() -> None:
    from src.providers.config import ProviderSpec

    spec = ProviderSpec.model_validate(
        {
            "base": "google-genai",
            "enabled": True,
            "quota_source": "https://aistudio.google.com/rate-limit",
            "quota_last_verified": None,
            "models": [
                {
                    "id": "gemini-3.8-flash",
                    "family": "gemini",
                    "roles": ["solver"],
                    "limits": {
                        "rpm": None,
                        "rpd": None,
                        "tpm": None,
                        "context_tokens": None,
                    },
                }
            ],
        }
    )
    result = keys_mod._build_key_metadata_verification(
        "gemini",
        spec,
        ["gemini-3.8-flash"],
        {"gemini-3.8-flash": {"context_tokens": 1_000_000, "output_tokens": 64_000}},
        {},
        {},
    )
    assert result.models[0].available is True
    assert result.models[0].context_tokens == 1_000_000
    assert result.models[0].output_tokens == 64_000
    assert result.unverified_fields == ["rpm", "rpd", "tpm"]
    assert result.quota_metadata_ready is False
    assert "quota_last_verified" in (result.quota_metadata_issue or "")
    assert "do not change shared models.yaml" in result.note


def test_groq_verification_maps_documented_headers_without_inventing_rpm() -> None:
    from src.providers.config import ProviderSpec

    spec = ProviderSpec.model_validate(
        {
            "base": "openai-compatible",
            "url": "https://api.groq.com/openai/v1",
            "enabled": True,
            "quota_source": "https://console.groq.com/docs/rate-limits",
            "quota_last_verified": "2026-11-17",
            "models": [
                {
                    "id": "openai/gpt-oss-20b",
                    "family": "gpt-oss",
                    "roles": ["solver"],
                    "limits": {
                        "rpm": 30,
                        "rpd": 1000,
                        "tpm": 8000,
                        "context_tokens": 8000,
                    },
                }
            ],
        }
    )
    result = keys_mod._build_key_metadata_verification(
        "groq",
        spec,
        ["openai/gpt-oss-20b"],
        {"openai/gpt-oss-20b": {"context_tokens": 131_072}},
        {
            "x-ratelimit-limit-requests": "14400",
            "x-ratelimit-limit-tokens": "18000",
            "authorization": "Bearer SECRET_CANARY_12345",
            "x-ratelimit-remaining-requests": "14000",
        },
        {},
    )
    by_field = {item.field: item for item in result.observed_quotas}
    assert by_field["rpd"].value == 14400
    assert by_field["rpd"].scope == "organization"
    assert by_field["tpm"].value == 18000
    assert "rpm" in result.unverified_fields
    assert "rpm" not in by_field
    assert all("SECRET_CANARY" not in item.source for item in result.observed_quotas)
    assert result.models[0].context_tokens == 131_072


def test_openrouter_verification_keeps_free_daily_cap_distinct_from_rpd() -> None:
    from src.providers.config import ProviderSpec

    spec = ProviderSpec.model_validate(
        {
            "base": "openai-compatible",
            "url": "https://openrouter.ai/api/v1",
            "enabled": True,
            "quota_source": "https://openrouter.ai/pricing",
            "quota_last_verified": "2026-11-17",
            "models": [
                {
                    "id": "google/gemma-4-26b-a4b-it:free",
                    "family": "gemma",
                    "roles": ["solver"],
                    "scope": "account",
                    "limits": {
                        "rpm": 20,
                        "rpd": 50,
                        "tpm": "unlimited",
                        "context_tokens": 262144,
                    },
                }
            ],
        }
    )
    result = keys_mod._build_key_metadata_verification(
        "openrouter",
        spec,
        ["google/gemma-4-26b-a4b-it:free"],
        {},
        {},
        {"free_model_requests_per_day": 50},
    )
    assert len(result.observed_quotas) == 1
    assert result.observed_quotas[0].field == "free_model_requests_per_day"
    assert result.observed_quotas[0].value == 50
    assert result.observed_quotas[0].scope == "account (free-model policy)"
    assert "rpd" in result.unverified_fields


def test_disabled_provider_key_can_be_verified_without_enabling_routing(
    monkeypatch, fake_key: str
) -> None:
    from src.providers.config import load_models_config

    catalog = load_models_config()
    cerebras = catalog.providers["cerebras"]
    disabled_cerebras = cerebras.model_copy(update={"enabled": False})
    config = catalog.model_copy(
        update={
            "providers": {
                **catalog.providers,
                "cerebras": disabled_cerebras,
            }
        }
    )
    monkeypatch.setattr(keys_mod, "load_models_config", lambda: config)
    model = config.providers["cerebras"].models[0].id

    async def _fake_openai(_url: str, _key: str, _headers: dict[str, str]):
        return 200, [model], False, {}, {}

    monkeypatch.setattr(keys_mod, "_list_openai", _fake_openai)
    response = _client(monkeypatch).post(
        "/api/keys/test",
        json={"provider": "cerebras", "key": fake_key},
    )

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["valid"] is True
    assert body["verification"]["provider_enabled"] is False
    assert body["verification"]["quota_metadata_ready"] is False
    assert "disabled" in body["verification"]["quota_metadata_issue"]
    assert "still disabled" in body["message"]
    assert fake_key not in response.text


@pytest.mark.parametrize(
    (
        "provider",
        "status_code",
        "has_invalid_key_marker",
        "expected_error",
        "expected_rate_limited",
    ),
    [
        ("gemini", 400, True, "auth_error", False),
        ("gemini", 400, False, "bad_response", False),  # malformed/non-specific 400
        ("groq", 400, True, "auth_error", False),
        ("gemini", 429, False, "rate_limited", True),
        ("groq", 401, False, "auth_error", False),
        ("groq", 429, False, "rate_limited", True),
        ("groq", 502, False, "unreachable", False),
        ("huggingface", 401, False, "auth_error", False),
        ("huggingface", 429, False, "rate_limited", True),
        ("huggingface", 500, False, "unreachable", False),
    ],
)
@respx.mock
def test_upstream_error_payloads_are_not_returned_or_logged(
    monkeypatch: pytest.MonkeyPatch,
    fake_key: str,
    caplog: LogCaptureFixture,
    provider: str,
    status_code: int,
    has_invalid_key_marker: bool,
    expected_error: str,
    expected_rate_limited: bool,
) -> None:
    """Only normalized classifications cross the provider/API boundary."""
    marker = "UPSTREAM_SECRET_CANARY_987654"
    response_text = f"provider diagnostic body {marker}"

    async def allow_rate_limit(*_args, **_kwargs) -> None:
        return None

    monkeypatch.setattr(keys_mod, "check_rate_limit", allow_rate_limit)
    if provider in ("gemini", "groq"):
        payload = (
            {
                "error": {
                    "code": "API_KEY_INVALID",
                    "message": f"API_KEY_INVALID {response_text}",
                }
            }
            if has_invalid_key_marker
            else None
        )
        upstream = (
            httpx.Response(status_code, json=payload)
            if payload is not None
            else httpx.Response(status_code, text=response_text)
        )
        url = (
            keys_mod._GEMINI_LIST_URL
            if provider == "gemini"
            else "https://api.groq.com/openai/v1/models"
        )
        respx.get(url).mock(return_value=upstream)
    else:
        from src.providers.config import load_models_config

        model = load_models_config().providers["huggingface"].models[0].id
        respx.get(keys_mod._HF_MODEL_URL.format(model=model)).mock(
            return_value=httpx.Response(status_code, text=response_text)
        )

    with caplog.at_level(logging.INFO, logger="assembly"):
        response = _client(monkeypatch).post(
            "/api/keys/test", json={"provider": provider, "key": fake_key}
        )

    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["error_code"] == expected_error
    assert payload["rate_limited"] is expected_rate_limited
    assert marker not in response.text
    assert marker not in caplog.text


@respx.mock
def test_gemini_nested_error_info_reason_classifies_invalid_key_without_leak(
    monkeypatch: pytest.MonkeyPatch,
    fake_key: str,
    caplog: LogCaptureFixture,
) -> None:
    """Google's nested ErrorInfo reason is used without retaining its payload."""
    marker = "NESTED_PROVIDER_DIAGNOSTIC_CANARY"

    async def allow_rate_limit(*_args, **_kwargs) -> None:
        return None

    monkeypatch.setattr(keys_mod, "check_rate_limit", allow_rate_limit)
    respx.get(keys_mod._GEMINI_LIST_URL).mock(
        return_value=httpx.Response(
            400,
            json={
                "error": {
                    "code": 400,
                    "status": "INVALID_ARGUMENT",
                    "message": "Request had an invalid argument.",
                    "details": [
                        {
                            "@type": "type.googleapis.com/google.rpc.ErrorInfo",
                            "reason": "API_KEY_INVALID",
                            "domain": "googleapis.com",
                            "metadata": {"diagnostic": marker},
                        }
                    ],
                }
            },
        )
    )

    with caplog.at_level(logging.INFO, logger="assembly"):
        response = _client(monkeypatch).post(
            "/api/keys/test", json={"provider": "gemini", "key": fake_key}
        )

    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["valid"] is False
    assert payload["error_code"] == "auth_error"
    assert marker not in response.text
    assert marker not in caplog.text
    assert fake_key not in response.text
    assert fake_key not in caplog.text
