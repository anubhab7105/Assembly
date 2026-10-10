"""Prompt A tests: web BYOK enforcement, per-request search keys, BLOCKED 400,
per-mode quota salt. All offline (mock routers/stubs, no provider network)."""

import logging
import os
import stat

import pytest
from fastapi.testclient import TestClient
from pydantic import SecretStr

CANARY_SEARCH = "tvly-CANARY-SEARCH-A1B2C3"
CANARY_PROV = "gsk-CANARY-PROV-D4E5F6"
CANARY_Q = "Canary prompt-a question ZULU-77: why do hummingbirds hum?"


@pytest.fixture()
def web_mode(monkeypatch, tmp_path):
    from src.core.config import settings

    monkeypatch.setattr(settings, "app_mode", "web")
    monkeypatch.setattr(settings, "app_env", "development")
    monkeypatch.setattr(settings, "debug", False)
    monkeypatch.setattr(settings, "allow_server_search_key", False)
    monkeypatch.chdir(tmp_path)
    yield settings


def _reset_salt():
    from src.providers import quota as quota_mod

    quota_mod.reset_quota_salt_cache()


@pytest.fixture(autouse=True)
def _clean_salt_cache():
    _reset_salt()
    yield
    _reset_salt()


# ── 1. Web ignores server-side search key by default ─────────────────────

def test_web_ignores_server_tavily_key(web_mode, monkeypatch) -> None:
    from src.core.config import settings
    from src.research.search import SearchEngine

    monkeypatch.setattr(settings, "tavily_api_key", SecretStr(CANARY_SEARCH))
    engine = SearchEngine()
    assert engine.has_tavily is False


def test_allow_flag_restores_server_tavily_key(web_mode, monkeypatch) -> None:
    from src.core.config import settings
    from src.research.search import SearchEngine

    monkeypatch.setattr(settings, "tavily_api_key", SecretStr(CANARY_SEARCH))
    monkeypatch.setattr(settings, "allow_server_search_key", True)
    engine = SearchEngine()
    assert engine.has_tavily is True


def test_explicit_search_key_wins_in_web_mode(web_mode, monkeypatch) -> None:
    from src.core.config import settings
    from src.core.keystore import reveal
    from src.research.search import SearchEngine

    monkeypatch.setattr(settings, "tavily_api_key", SecretStr(""))
    engine = SearchEngine(tavily_key=CANARY_SEARCH)
    assert engine.has_tavily is True
    assert reveal(engine.tavily_key) == CANARY_SEARCH


# ── 2. Web startup fails with server-side provider keys ──────────────────

def test_web_startup_fails_with_provider_key_in_env(web_mode, monkeypatch) -> None:
    from src.core.keystore import enforce_web_key_policy

    monkeypatch.setenv("GROQ_API_KEY", CANARY_PROV)
    with pytest.raises(RuntimeError, match="BYOK"):
        enforce_web_key_policy()


def test_web_startup_fails_with_provider_key_in_settings(web_mode, monkeypatch) -> None:
    from src.core.config import settings
    from src.core.keystore import enforce_web_key_policy

    monkeypatch.delenv("GROQ_API_KEY", raising=False)
    monkeypatch.setattr(settings, "groq_api_key", SecretStr(CANARY_PROV))
    with pytest.raises(RuntimeError, match="BYOK"):
        enforce_web_key_policy()


def test_dev_mode_keeps_env_keys(monkeypatch) -> None:
    from src.core.config import settings
    from src.core.keystore import enforce_web_key_policy

    monkeypatch.setattr(settings, "app_mode", "dev")
    monkeypatch.setenv("GROQ_API_KEY", CANARY_PROV)
    enforce_web_key_policy()  # must not raise


def test_web_tavily_warning_once(web_mode, monkeypatch, caplog) -> None:
    from src.core.config import settings
    from src.core.keystore import enforce_web_key_policy, provider_key_env_names

    for name in provider_key_env_names():
        monkeypatch.delenv(name, raising=False)
        monkeypatch.setattr(settings, name.lower(), SecretStr(""))
    monkeypatch.setattr(settings, "tavily_api_key", SecretStr(CANARY_SEARCH))
    with caplog.at_level(logging.WARNING, logger="assembly"):
        enforce_web_key_policy()  # warns, does not raise
    assert "TAVILY_API_KEY" in caplog.text
    assert CANARY_SEARCH not in caplog.text


# ── 3. search_keys never leak (logs / 422) ───────────────────────────────

def test_search_keys_absent_from_422(web_mode, caplog) -> None:
    from src.main import app

    client = TestClient(app)
    with caplog.at_level(logging.INFO, logger="assembly"):
        res = client.post(
            "/api/run",
            json={
                "question": "",
                "time_budget_minutes": 3,
                "provider_keys": {"groq": CANARY_PROV},
                "search_keys": {"tavily": CANARY_SEARCH},
            },
        )
    assert res.status_code == 422
    assert CANARY_SEARCH not in res.text
    assert CANARY_PROV not in res.text
    assert CANARY_SEARCH not in caplog.text
    assert CANARY_PROV not in caplog.text


def test_search_keys_flow_to_tavily_without_logging(web_mode, monkeypatch, caplog) -> None:
    import src.api.run as run_mod
    from src.main import app
    from src.providers.mock_provider import MockProvider
    from src.research import providers as search_providers_mod
    from tests.conftest import MockRouter

    seen: dict[str, str] = {}
    real_init = search_providers_mod.TavilySearchProvider.__init__

    def _spy(self, api_key=None):
        real_init(self, api_key=api_key)
        from src.core.keystore import reveal

        seen["tavily"] = reveal(self._api_key)

    async def _no_http(self, query: str, max_results: int = 5):
        raise AssertionError("must not reach the network in this test")

    def _fake(provider_keys, allowed, pins):
        return MockRouter(
            [MockProvider(provider_name="mock-a"), MockProvider(provider_name="mock-b")]
        )

    monkeypatch.setattr(run_mod, "_filtered_router", _fake)
    monkeypatch.setattr(search_providers_mod.TavilySearchProvider, "__init__", _spy)
    monkeypatch.setattr(search_providers_mod.TavilySearchProvider, "search", _no_http)
    client = TestClient(app)
    with caplog.at_level(logging.INFO, logger="assembly"):
        res = client.post(
            "/api/run",
            json={
                "question": CANARY_Q,
                "time_budget_minutes": 3,
                "provider_keys": {"groq": CANARY_PROV},
                "search_keys": {"tavily": CANARY_SEARCH},
                "model_selection": {"selected": [], "pins": {}},
                "usage_snapshot": [],
            },
        )
    # Mock router has no diversity gate; catalog fallback is not blocked.
    assert res.status_code == 200, res.text
    assert seen.get("tavily") == CANARY_SEARCH
    assert CANARY_SEARCH not in caplog.text
    assert CANARY_PROV not in caplog.text


# ── 4. Keyless research end to end with mocks ────────────────────────────

class _StubSearchProvider:
    """Offline stand-in for a keyless search backend (no network)."""

    def __init__(self, name: str, hits: int = 1) -> None:
        self.provider_name = name
        self._hits = hits
        self.calls = 0

    @property
    def is_available(self) -> bool:
        return True

    async def search(self, query: str, max_results: int = 5):
        from src.research.schemas import SearchResult

        self.calls += 1
        return [
            SearchResult(title=f"{self.provider_name} hit", url="https://example.com/x", snippet="s")
            for _ in range(self._hits)
        ]


async def test_keyless_research_uses_keyless_providers() -> None:
    from src.research.router import SearchRouter, default_providers

    providers = default_providers(tavily_key="")
    tavily = next(p for p in providers if p.provider_name == "tavily")
    assert tavily.is_available is False
    keyless = [_StubSearchProvider("wikipedia"), _StubSearchProvider("arxiv")]
    router = SearchRouter(providers=[tavily, *keyless])
    results = await router.search("mock offline query", problem_type="research")
    assert len(results) == 1
    # Academic order serves arxiv before wikipedia; exactly one rang.
    assert router.last_providers_used == ["arxiv"]
    assert keyless[1].calls == 1
    assert keyless[0].calls == 0


async def test_tavily_without_key_never_calls_http(monkeypatch) -> None:
    import httpx

    from src.research.providers import SearchProviderError, TavilySearchProvider

    provider = TavilySearchProvider(api_key="")
    assert provider.is_available is False

    def _forbidden(*args, **kwargs):
        raise AssertionError("no HTTP without a key")

    monkeypatch.setattr(httpx, "AsyncClient", _forbidden)
    with pytest.raises(SearchProviderError):
        await provider.search("mock query")


# ── 5. BLOCKED returns 400 ───────────────────────────────────────────────

def test_blocked_returns_400_with_code(web_mode, caplog) -> None:
    from src.main import app

    client = TestClient(app)
    with caplog.at_level(logging.INFO, logger="assembly"):
        res = client.post(
            "/api/run",
            json={
                "question": CANARY_Q,
                "time_budget_minutes": 3,
                "provider_keys": {},
                "model_selection": {"selected": [], "pins": {}},
                "usage_snapshot": [],
            },
        )
    assert res.status_code == 400, res.text
    body = res.json()
    assert body["code"] == "blocked_no_usable_keys"
    assert "model families" in body["detail"]
    assert body["minimum_families"] == 3
    # No provider call was attempted and nothing sensitive echoed.
    assert "generating" not in caplog.text
    assert CANARY_Q not in res.text


# ── 6. Salt per mode ─────────────────────────────────────────────────────

def test_explicit_salt_wins_everywhere(monkeypatch) -> None:
    from src.core.config import settings
    from src.providers import quota as quota_mod

    monkeypatch.setattr(settings, "app_mode", "web")
    monkeypatch.setenv("QUOTA_SALT", "explicit-salt-A1")
    assert quota_mod.get_quota_salt() == "explicit-salt-A1"


def test_web_salt_random_per_process(monkeypatch) -> None:
    from src.core.config import settings
    from src.providers import quota as quota_mod

    monkeypatch.setattr(settings, "app_mode", "web")
    monkeypatch.delenv("QUOTA_SALT", raising=False)
    monkeypatch.setattr(settings, "quota_salt", SecretStr(""))
    first = quota_mod.get_quota_salt()
    assert first and first != "assembly-dev-quota"
    assert quota_mod.get_quota_salt() == first
    assert quota_mod.fingerprint_key("k") == quota_mod.fingerprint_key("k")


def test_desktop_salt_persists_with_tight_permissions(monkeypatch, tmp_path) -> None:
    from src.core.config import settings
    from src.providers import quota as quota_mod

    _reset_salt()
    target = tmp_path / "quota_salt"
    monkeypatch.setattr(settings, "app_mode", "desktop")
    monkeypatch.delenv("QUOTA_SALT", raising=False)
    monkeypatch.setattr(settings, "quota_salt", SecretStr(""))
    monkeypatch.setattr(quota_mod, "_desktop_salt_path", lambda: target)
    first = quota_mod.get_quota_salt()
    assert first and first != "assembly-dev-quota"
    assert target.is_file()
    if os.name == "posix":
        mode = stat.S_IMODE(target.stat().st_mode)
        assert mode & 0o077 == 0, f"group/other permissions set: {oct(mode)}"
    assert quota_mod.get_quota_salt() == first


def test_salt_never_empty_or_constant(monkeypatch, tmp_path) -> None:
    from src.core.config import settings
    from src.providers import quota as quota_mod

    for mode in ("web", "desktop", "dev"):
        monkeypatch.setattr(settings, "app_mode", mode)
        monkeypatch.delenv("QUOTA_SALT", raising=False)
        monkeypatch.setattr(settings, "quota_salt", SecretStr(""))
        if mode == "desktop":
            target = tmp_path / f"salt-{mode}"
            monkeypatch.setattr(quota_mod, "_desktop_salt_path", lambda: target)
        salt = quota_mod.get_quota_salt()
        assert salt not in ("", "assembly-dev-quota")
