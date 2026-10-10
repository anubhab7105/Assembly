"""
Assembly — API key storage backends (TECH_STACK.md section 5, BYOK).

Keys are wrapped in pydantic SecretStr from the moment they enter the
backend: repr() and str() show '**********', never the value. The raw
value is revealed only at the single call site that talks to a provider.

Backends (selected by APP_MODE):
- dev:     EnvKeyStore — process environment via settings (developer only;
           refuses to even construct when app_env is production).
- web:     RequestKeyStore — keys arrive per execution request, live in
           memory for that run only, and are wiped in a finally path.
- desktop: KeyringKeyStore — Windows Credential Manager via `keyring`;
           keys never touch plain files or .env.
"""

from abc import ABC, abstractmethod
from collections.abc import Mapping

from pydantic import SecretStr

KeyValue = str | SecretStr | None
KeyMap = dict[str, SecretStr]


def reveal(value: KeyValue) -> str:
    """Unwrap a key for the single provider call site. Never log the result."""
    if value is None:
        return ""
    if isinstance(value, SecretStr):
        return value.get_secret_value()
    return value


def wrap_keys(raw: Mapping[str, KeyValue]) -> KeyMap:
    """Normalize incoming keys to SecretStr, silently dropping empties."""
    wrapped: KeyMap = {}
    for provider, key in raw.items():
        value = reveal(key)
        if value:
            wrapped[provider] = key if isinstance(key, SecretStr) else SecretStr(value)
    return wrapped


class KeyStore(ABC):
    """Key storage backend interface."""

    @abstractmethod
    def get_keys(self) -> KeyMap:
        """Return provider id → SecretStr for every key held."""

    @abstractmethod
    def set_key(self, provider: str, key: KeyValue) -> None:
        """Store (or replace) one key."""

    @abstractmethod
    def has(self, provider: str) -> bool:
        """Check whether a usable key is held, without revealing it."""

    def providers(self) -> list[str]:
        """Ids with a usable key, sorted. Names only — never values."""
        return sorted(self.get_keys())

    @abstractmethod
    def clear(self) -> None:
        """Drop everything held (memory wipe / delete from backend)."""


class RequestKeyStore(KeyStore):
    """Web mode: keys live in memory for one execution only."""

    def __init__(self, keys: Mapping[str, KeyValue] | None = None) -> None:
        self._keys: KeyMap = wrap_keys(keys or {})

    def get_keys(self) -> KeyMap:
        return dict(self._keys)

    def set_key(self, provider: str, key: KeyValue) -> None:
        value = reveal(key)
        if value:
            self._keys[provider] = (
                key if isinstance(key, SecretStr) else SecretStr(value)
            )
        else:
            self._keys.pop(provider, None)

    def has(self, provider: str) -> bool:
        return provider in self._keys

    def clear(self) -> None:
        self._keys.clear()


class KeyringKeyStore(KeyStore):
    """Desktop mode: OS-encrypted storage (Windows Credential Manager)."""

    def __init__(self, service: str = "Assembly") -> None:
        self._service = service

    def _backend(self):  # type: ignore[no-untyped-def]
        """Lazy import so the backend is only required in desktop mode."""
        try:
            import keyring
        except ImportError as exc:
            raise RuntimeError(
                "The 'keyring' library is not installed; desktop key storage "
                "needs it (pip install keyring, plus pywin32 on Windows)."
            ) from exc
        return keyring

    def _catalog_ids(self) -> list[str]:
        try:
            from src.providers.config import load_models_config

            return list(load_models_config().providers)
        except Exception:  # noqa: BLE001 — catalog trouble means no keyring listing
            return []

    def get_keys(self) -> KeyMap:
        backend = self._backend()
        keys: KeyMap = {}
        for provider in self._catalog_ids():
            value = backend.get_password(self._service, provider)
            if value:
                keys[provider] = SecretStr(value)
        return keys

    def set_key(self, provider: str, key: KeyValue) -> None:
        value = reveal(key)
        if value:
            self._backend().set_password(self._service, provider, value)
        else:
            self.delete(provider)

    def delete(self, provider: str) -> None:
        try:
            self._backend().delete_password(self._service, provider)
        except Exception:  # noqa: BLE001, S110 — deleting a missing entry is fine
            pass

    def has(self, provider: str) -> bool:
        try:
            return bool(self._backend().get_password(self._service, provider))
        except Exception:  # noqa: BLE001 — an unreadable keyring reads as "no key"
            return False

    def clear(self) -> None:
        for provider in self._catalog_ids():
            self.delete(provider)


class EnvKeyStore(KeyStore):
    """Developer mode: keys from the process environment (via settings).

    Refuses to construct when app_env is production — production must use
    per-request (web) or OS-keyring (desktop) keys, never env keys.
    """

    def __init__(self) -> None:
        from src.core.config import settings

        if settings.is_production:
            raise RuntimeError(
                "EnvKeyStore is developer-mode only and refuses to start when "
                "APP_ENV is production. Use web (per-request keys) or desktop "
                "(OS keyring) mode instead."
            )
        self._owned: set[str] = set()

    @staticmethod
    def _key_attrs() -> dict[str, str]:
        return {
            "gemini": "gemini_api_key",
            "groq": "groq_api_key",
            "cerebras": "cerebras_api_key",
            "openrouter": "openrouter_api_key",
            "huggingface": "huggingface_api_key",
        }

    def get_keys(self) -> KeyMap:
        from src.core.config import settings

        keys: KeyMap = {}
        for provider, attr in self._key_attrs().items():
            value = getattr(settings, attr, SecretStr(""))
            if not isinstance(value, SecretStr):
                value = SecretStr(reveal(value))
            if reveal(value):
                keys[provider] = value
        return keys

    def set_key(self, provider: str, key: KeyValue) -> None:
        import os

        value = reveal(key)
        if value:
            os.environ[f"{provider.upper()}_API_KEY"] = value
            self._owned.add(provider)

    def has(self, provider: str) -> bool:
        return provider in self.get_keys()

    def clear(self) -> None:
        import os

        for provider in list(self._owned):
            os.environ.pop(f"{provider.upper()}_API_KEY", None)
        self._owned.clear()


def get_keystore(mode: str | None = None) -> KeyStore:
    """Select the backend for an APP_MODE (dev | web | desktop)."""
    from src.core.config import settings

    resolved = mode or settings.app_mode
    if resolved == "dev":
        return EnvKeyStore()
    if resolved == "web":
        return RequestKeyStore()
    if resolved == "desktop":
        return KeyringKeyStore()
    raise ValueError(f"unknown APP_MODE {resolved!r}; expected dev, web, or desktop")


def provider_key_env_names() -> list[str]:
    """Server-side provider-key variable names (never values)."""
    return [f"{provider.upper()}_API_KEY" for provider in EnvKeyStore._key_attrs()]


def server_keys_present() -> list[str]:
    """Provider/search key variable names set in this process (names only).

    Checks the process environment and the loaded settings (which may have
    read a dotenv file). Never returns values.
    """
    import os

    from src.core.config import settings

    found: list[str] = []
    for name in provider_key_env_names():
        if os.environ.get(name):
            found.append(name)
            continue
        try:
            if reveal(getattr(settings, name.lower(), None)):
                found.append(name)
        except Exception:  # noqa: BLE001 — one unreadable field skips
            continue
    return found


def enforce_web_key_policy() -> None:
    """Fail web-mode startup when server-side provider keys are configured.

    Web mode is BYOK: provider keys must arrive per request, never from the
    server environment or files. Raises RuntimeError naming the offending
    variables (names only, never values). Desktop/dev modes are unaffected.

    A server-side Tavily key is not fatal: it is ignored unless
    ALLOW_SERVER_SEARCH_KEY is set (see resolve_tavily_key), with one
    startup warning here.
    """
    from src.core.config import settings
    from src.core.logging_config import logger

    if not settings.is_web:
        return
    offenders = server_keys_present()
    if offenders:
        raise RuntimeError(
            "Web mode is BYOK: server-side provider keys are configured "
            f"({', '.join(sorted(offenders))}). Unset them; clients send "
            "keys per request."
        )
    import os

    tavily_set = bool(os.environ.get("TAVILY_API_KEY")) or bool(
        reveal(settings.tavily_api_key)
    )
    if tavily_set and not settings.allow_server_search_key:
        logger.warning(
            "Server   │ TAVILY_API_KEY is set but ALLOW_SERVER_SEARCH_KEY "
            "is false — the server key will be ignored in web mode."
        )


def resolve_tavily_key(explicit: KeyValue = None) -> SecretStr:
    """Per-request Tavily key if given, else the server key where allowed.

    Web mode ignores the server-side key unless ALLOW_SERVER_SEARCH_KEY is
    set. Never logs the value; callers must treat the result as secret.
    """
    if reveal(explicit):
        return explicit if isinstance(explicit, SecretStr) else SecretStr(reveal(explicit))
    from src.core.config import settings

    if settings.is_web and not settings.allow_server_search_key:
        return SecretStr("")
    return settings.tavily_api_key
