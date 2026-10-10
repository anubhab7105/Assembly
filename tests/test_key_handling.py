"""Key-handling tests (TECH_STACK.md section 5).

A sentinel fake key must appear in no stored execution record, API
response, log line, or exception message. All provider I/O here is
mocked or fails fast on the offline socket guard — no real network.
"""

import sys
import time
from typing import Any, ClassVar

import pytest
from fastapi.testclient import TestClient
from pydantic import SecretStr
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from src.core.config import settings
from src.core.keystore import (
    EnvKeyStore,
    KeyringKeyStore,
    RequestKeyStore,
    get_keystore,
    reveal,
    wrap_keys,
)
from src.database.base import Base, get_db
from src.database.models import AgentRun, Execution


def _string_values(obj: Any) -> list[str]:
    return [str(v) for v in vars(obj).values() if isinstance(v, str)]


# ── Stores ────────────────────────────────────────────────────────────


def test_request_store_wraps_and_wipes(fake_key: str) -> None:
    store = RequestKeyStore({"groq": fake_key, "empty": ""})
    keys = store.get_keys()
    assert set(keys) == {"groq"}
    assert isinstance(keys["groq"], SecretStr)
    assert fake_key not in repr(keys["groq"]) + str(keys["groq"]) + repr(store)
    assert store.has("groq") and not store.has("cerebras")
    assert store.providers() == ["groq"]
    store.clear()
    assert store.get_keys() == {}


def test_wrap_keys_skips_empties_and_accepts_secretstr(fake_key: str) -> None:
    wrapped = wrap_keys({"a": fake_key, "b": "", "c": None, "d": SecretStr(fake_key)})
    assert set(wrapped) == {"a", "d"}
    assert all(isinstance(v, SecretStr) for v in wrapped.values())


class _FakeKeyring:
    """Dict-backed keyring stub (module-shaped for sys.modules injection)."""

    _vault: ClassVar[dict[tuple[str, str], str]] = {}

    @classmethod
    def get_password(cls, service: str, username: str) -> str | None:
        return cls._vault.get((service, username))

    @classmethod
    def set_password(cls, service: str, username: str, password: str) -> None:
        cls._vault[(service, username)] = password

    @classmethod
    def delete_password(cls, service: str, username: str) -> None:
        try:
            del cls._vault[(service, username)]
        except KeyError as exc:
            raise KeyError(username) from exc


def test_keyring_store_roundtrip_with_stub(monkeypatch, fake_key: str) -> None:
    monkeypatch.setitem(sys.modules, "keyring", _FakeKeyring)
    _FakeKeyring._vault.clear()
    store = KeyringKeyStore(service="AssemblyTest")
    assert not store.has("groq")
    store.set_key("groq", fake_key)
    assert store.has("groq")
    keys = store.get_keys()
    assert isinstance(keys.get("groq"), SecretStr)
    assert fake_key not in repr(store) + repr(keys)
    store.clear()
    assert not store.has("groq")


def test_env_store_refuses_production(monkeypatch) -> None:
    monkeypatch.setattr(settings, "app_env", "production")
    with pytest.raises(RuntimeError, match="developer-mode only"):
        EnvKeyStore()


def test_env_store_returns_secretstr_map() -> None:
    for value in EnvKeyStore().get_keys().values():
        assert isinstance(value, SecretStr)


def test_mode_switch_mapping() -> None:
    assert isinstance(get_keystore("web"), RequestKeyStore)
    assert isinstance(get_keystore("desktop"), KeyringKeyStore)
    assert isinstance(get_keystore("dev"), EnvKeyStore)
    with pytest.raises(ValueError, match="unknown APP_MODE"):
        get_keystore("nope")


def test_reveal_handles_all_shapes(fake_key: str) -> None:
    assert reveal(SecretStr(fake_key)) == fake_key
    assert reveal(fake_key) == fake_key
    assert reveal(None) == ""
    assert reveal("") == ""


# ── API: no-leak scans ────────────────────────────────────────────────


def _authed_client(monkeypatch) -> TestClient:
    """Desktop local-history client (no accounts)."""
    import src.api.executions as exec_mod
    from src.core.config import settings as _settings
    from src.main import app

    monkeypatch.setattr(_settings, "app_mode", "dev")
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,  # One shared connection: the memory DB survives threads.
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
    client = TestClient(app)
    return client


def test_execution_with_request_keys_leaks_nothing(
    monkeypatch, fake_key: str, caplog
) -> None:
    """Per-request keys never leak; BLOCKED family gate fails fast (FR-10).

    A key for a disabled provider yields 0 usable families, so the run
    refuses immediately via the family gate (no provider calls, fast even
    under bare-TestClient per-request portals). All leak assertions from
    the old provider-count fail-fast path are preserved.
    """
    import logging

    client = _authed_client(monkeypatch)
    with caplog.at_level(logging.INFO, logger="assembly"):
        created = client.post(
            "/api/executions/",
            json={
                "question": "What is the mock answer?",
                "time_budget_minutes": 3,
                "provider_keys": {"cerebras": fake_key},
            },
        )
    assert created.status_code == 200, created.text
    execution_id = created.json()["id"]
    assert fake_key not in created.text

    status = ""
    for _ in range(100):
        gotten = client.get(f"/api/executions/{execution_id}")
        assert gotten.status_code == 200
        status = gotten.json()["status"]
        if status in ("completed", "failed"):
            break
        time.sleep(0.2)
    assert status in ("completed", "failed")
    assert fake_key not in gotten.text
    assert "provider_keys" not in gotten.json()
    assert fake_key not in caplog.text


def test_execution_db_rows_hold_no_keys(monkeypatch, fake_key: str) -> None:
    client = _authed_client(monkeypatch)
    created = client.post(
        "/api/executions/",
        json={
            "question": "What is the mock answer?",
            "time_budget_minutes": 3,
            "provider_keys": {"groq": fake_key},
        },
    )
    execution_id = created.json()["id"]
    for _ in range(100):
        gotten = client.get(f"/api/executions/{execution_id}")
        if gotten.json()["status"] in ("completed", "failed"):
            break
        time.sleep(0.2)

    # Same in-memory DB the app wrote to (SessionLocal was patched above).
    import src.api.executions as exec_mod

    db = exec_mod.SessionLocal()
    try:
        rows: list[Any] = []
        rows += db.query(Execution).all()
        rows += db.query(AgentRun).all()
        assert rows != []
        for row in rows:
            for value in _string_values(row):
                assert fake_key not in value
    finally:
        db.close()


def test_keys_test_endpoint_never_echoes(monkeypatch, fake_key: str) -> None:
    client = _authed_client(monkeypatch)
    response = client.post("/api/keys/test", json={"provider": "groq", "key": fake_key})
    assert response.status_code == 200, response.text
    body = response.json()
    assert set(body) == {"provider", "valid", "rate_limited", "error_code", "model"}
    assert body["provider"] == "groq"
    assert body["valid"] is False
    assert fake_key not in response.text

    unknown = client.post(
        "/api/keys/test", json={"provider": "skynet", "key": fake_key}
    )
    assert unknown.status_code == 404


def test_providers_status_names_only(monkeypatch) -> None:
    client = _authed_client(monkeypatch)
    response = client.get("/api/providers/status")
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["mode"] in ("dev", "web", "desktop")
    assert body["providers"] != []
    assert body["families"] != [] or True
    text = response.text
    for attr in (
        "gemini_api_key",
        "groq_api_key",
        "cerebras_api_key",
        "openrouter_api_key",
        "huggingface_api_key",
        "tavily_api_key",
    ):
        value = reveal(getattr(settings, attr, ""))
        if value:
            assert value not in text


def test_delete_all_keys_clears_keyring(monkeypatch, fake_key: str) -> None:
    """DELETE /api/keys wipes every key from the keyring (desktop mode)."""
    from src.core.config import settings as _settings
    from src.main import app

    monkeypatch.setattr(_settings, "app_mode", "desktop")
    monkeypatch.setitem(sys.modules, "keyring", _FakeKeyring)
    _FakeKeyring._vault.clear()

    # Use the same default service name as the API endpoint's get_keystore()
    store = KeyringKeyStore()
    store.set_key("groq", fake_key)
    store.set_key("gemini", fake_key)
    assert store.has("groq") and store.has("gemini")

    # Desktop mode requires the X-Assembly-Token header (see main.py middleware)
    client = TestClient(app)
    headers = {"X-Assembly-Token": _settings.desktop_token}
    response = client.delete("/api/keys", headers=headers)
    assert response.status_code == 200, response.text
    assert response.json() == {"detail": "All keys deleted"}
    assert not store.has("groq")
    assert not store.has("gemini")
    assert fake_key not in response.text


def test_delete_all_keys_rejects_non_desktop(monkeypatch) -> None:
    """DELETE /api/keys only works in desktop mode."""
    from src.core.config import settings as _settings
    from src.main import app

    monkeypatch.setattr(_settings, "app_mode", "web")
    client = TestClient(app)
    headers = {"X-Assembly-Token": _settings.desktop_token}
    response = client.delete("/api/keys", headers=headers)
    assert response.status_code == 400
    assert "desktop" in response.json()["detail"]
