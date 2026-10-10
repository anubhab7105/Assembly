"""Gemini key-Test classification (mocked list probe, offline).

Only an authentication failure may report "invalid". Quota, model
availability, and transport problems each report their own state, and
pasted-key whitespace never turns a valid key invalid.
"""

import logging

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


def _stub_list(monkeypatch, status, ids, body=""):
    async def _fake(key: str):
        return status, ids, body

    monkeypatch.setattr(keys_mod, "_list_gemini", _fake)


def test_list_200_is_valid(monkeypatch, fake_key: str) -> None:
    _stub_list(monkeypatch, 200, ["gemini-3.8-flash"])
    res = _client(monkeypatch).post(
        "/api/keys/test", json={"provider": "gemini", "key": fake_key}
    )
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["valid"] is True
    assert body["rate_limited"] is False
    assert body["error_code"] is None
    assert body["model_available"] is True
    assert fake_key not in res.text


def test_list_200_missing_model_is_key_valid_with_alternatives(
    monkeypatch, fake_key: str
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
        '{"error": {"code": 400, "message": "API key not valid. API_KEY_INVALID"}}',
    )
    body = (
        _client(monkeypatch)
        .post("/api/keys/test", json={"provider": "gemini", "key": fake_key})
        .json()
    )
    assert body["valid"] is False
    assert body["error_code"] == "auth_error"


def test_list_401_is_invalid(monkeypatch, fake_key: str) -> None:
    _stub_list(monkeypatch, 401, [], '{"error": {"status": "UNAUTHENTICATED"}}')
    body = (
        _client(monkeypatch)
        .post("/api/keys/test", json={"provider": "gemini", "key": fake_key})
        .json()
    )
    assert body["valid"] is False
    assert body["error_code"] == "auth_error"


def test_list_403_is_invalid(monkeypatch, fake_key: str) -> None:
    _stub_list(monkeypatch, 403, [], '{"error": {"status": "PERMISSION_DENIED"}}')
    body = (
        _client(monkeypatch)
        .post("/api/keys/test", json={"provider": "gemini", "key": fake_key})
        .json()
    )
    assert body["valid"] is False
    assert body["error_code"] == "auth_error"


def test_list_429_is_quota_not_invalid(monkeypatch, fake_key: str) -> None:
    _stub_list(monkeypatch, 429, [], '{"error": {"status": "RESOURCE_EXHAUSTED"}}')
    body = (
        _client(monkeypatch)
        .post("/api/keys/test", json={"provider": "gemini", "key": fake_key})
        .json()
    )
    assert body["rate_limited"] is True
    assert body["error_code"] == "rate_limited"
    assert "quota or rate limit" in (body["message"] or "")


def test_list_404_model_is_key_valid(monkeypatch, fake_key: str) -> None:
    _stub_list(monkeypatch, 404, [], '{"error": {"status": "NOT_FOUND"}}')
    body = (
        _client(monkeypatch)
        .post("/api/keys/test", json={"provider": "gemini", "key": fake_key})
        .json()
    )
    assert body["valid"] is True
    assert body["error_code"] == "model_not_found"
    assert body["model_available"] is False


def test_list_timeout_is_unreachable_never_invalid(monkeypatch, fake_key: str) -> None:
    _stub_list(monkeypatch, None, [], "")
    body = (
        _client(monkeypatch)
        .post("/api/keys/test", json={"provider": "gemini", "key": fake_key})
        .json()
    )
    assert body["valid"] is False
    assert body["error_code"] == "unreachable"
    assert "reach" in (body["message"] or "")


def test_trailing_newline_key_is_trimmed_before_probe(monkeypatch) -> None:
    seen: dict[str, str] = {}

    async def _capture(key: str):
        seen["key"] = key
        return 200, ["gemini-3.8-flash"], ""

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


def test_canary_never_in_test_response_or_logs(monkeypatch, caplog) -> None:
    _stub_list(monkeypatch, 401, [], "unauthorized")
    with caplog.at_level(logging.INFO, logger="assembly"):
        res = _client(monkeypatch).post(
            "/api/keys/test", json={"provider": "gemini", "key": CANARY}
        )
    assert res.status_code == 200
    assert CANARY not in res.text
    assert CANARY not in caplog.text
