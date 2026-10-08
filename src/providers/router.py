"""
Assembly — Model Router (config-driven).

Selects the best provider + model for each agent role. All model ids,
families, roles, limits, and endpoints come from models.yaml
(src/providers/config.py) — nothing is hard-coded here.

Candidate order follows the catalog: provider order, then model order
inside each provider. List the fastest/cheapest model first per provider
in models.yaml and tight time budgets automatically get fast models.

Requires at least 3 live providers before accepting any work.
"""

from collections.abc import Mapping
from dataclasses import dataclass

from pydantic import SecretStr

from src.core.keystore import get_keystore, reveal
from src.core.logging_config import logger
from src.providers.base import AIProvider
from src.providers.config import ModelsConfig, load_models_config
from src.providers.registry import get_provider

MIN_REQUIRED_PROVIDERS = 3

# Key prefixes that mean "not configured" (mirrors Settings.has_provider).
_PLACEHOLDER_PREFIXES = (
    "sk-your",
    "your-",
    "gsk_your",
    "hf_your",
    "csk_your",
    "xpl_your",
)


@dataclass
class ModelAssignment:
    """Result of model routing: provider instance + specific model."""

    provider: AIProvider
    model: str
    provider_name: str
    family: str = ""


class ModelRouter:
    """
    Config-driven model selection engine.

    Routes agent roles to the best available provider/model combination.
    Requires at least 3 live providers to operate.
    """

    def __init__(
        self,
        config: ModelsConfig | None = None,
        keys: Mapping[str, str | SecretStr] | None = None,
    ) -> None:
        """Build the router. keys (provider → key) overrides the APP_MODE store.

        Keys arrive as SecretStr and are revealed only for provider
         construction — names alone are ever logged.
        """
        self.config = config or load_models_config()
        self._providers: dict[str, AIProvider] = {}
        self._init_providers(keys)

    @staticmethod
    def _mode_keys() -> dict[str, str]:
        """Keys for the current APP_MODE (dev: env, web: none, desktop: keyring).

        Web mode intentionally contributes no server keys — keys arrive
        per request. Failures reading the desktop keyring degrade to no
        keys rather than crashing startup.
        """
        try:
            store = get_keystore()
        except (ValueError, RuntimeError):
            return {}
        try:
            return {pid: reveal(value) for pid, value in store.get_keys().items()}
        except Exception:  # noqa: BLE001 — keyring trouble must not kill startup
            return {}

    def _init_providers(
        self, keys: Mapping[str, str | SecretStr] | None = None
    ) -> None:
        """Initialize every enabled provider that has a real API key."""
        key_map = (
            {pid: reveal(value) for pid, value in keys.items()}
            if keys is not None
            else self._mode_keys()
        )
        total = len(self.config.providers)
        for provider_id, spec in self.config.providers.items():
            if not spec.enabled:
                logger.info(
                    f"Router  │ ○ {provider_id} provider disabled in models.yaml"
                )
                continue
            key = key_map.get(provider_id, "")
            if not key or any(key.startswith(p) for p in _PLACEHOLDER_PREFIXES):
                logger.warning(f"Router  │ ✗ {provider_id} provider — no API key")
                continue
            try:
                provider = get_provider(provider_id, key, config=self.config)
                if provider.is_available():
                    self._providers[provider_id] = provider
                    logger.info(f"Router  │ ✓ {provider_id} provider available")
                else:
                    logger.warning(f"Router  │ ✗ {provider_id} provider — no API key")
            except Exception as e:  # noqa: BLE001 — one bad provider must not kill startup
                logger.warning(f"Router  │ ✗ {provider_id} provider — init error: {e}")

        live = len(self._providers)
        logger.info(
            f"Router  │ {live}/{total} providers live "
            f"(minimum required: {MIN_REQUIRED_PROVIDERS})"
        )
        if live < MIN_REQUIRED_PROVIDERS:
            logger.error(
                f"Router  │ ⚠ Only {live} provider(s) available. "
                f"Assembly requires at least {MIN_REQUIRED_PROVIDERS}. "
                f"Add more API keys to .env."
            )

    def get_available_providers(self) -> list[str]:
        """Return names of providers with valid credentials."""
        return list(self._providers.keys())

    def get_live_count(self) -> int:
        """Return the number of currently live providers."""
        return len(self._providers)

    def _enforce_minimum(self) -> None:
        """Raise an error if fewer than 3 providers are live."""
        live = len(self._providers)
        if live < MIN_REQUIRED_PROVIDERS:
            available = ", ".join(self._providers.keys()) if self._providers else "none"
            raise RuntimeError(
                f"Assembly requires at least {MIN_REQUIRED_PROVIDERS} AI providers to be live. "
                f"Currently only {live} available ({available}). "
                f"Please add more API keys to your .env file."
            )

    def _family_of(self, provider_id: str, model_id: str) -> str:
        """Look up the catalog family for a live provider/model pair."""
        for model in self.config.providers[provider_id].models:
            if model.id == model_id:
                return model.family
        return ""

    def _candidates(self, role: str) -> list[tuple[str, str, str]]:
        """(provider_id, model_id, family) for role, in catalog order."""
        candidates = []
        for provider_id, spec in self.config.providers.items():
            if provider_id not in self._providers:
                continue
            for model in spec.models:
                if role in model.roles:
                    candidates.append((provider_id, model.id, model.family))
        return candidates

    def _fallback(self) -> ModelAssignment:
        """First model of the first live provider (catalog order)."""
        provider_id = next(iter(self._providers))
        model_id = self.config.providers[provider_id].models[0].id
        return ModelAssignment(
            provider=self._providers[provider_id],
            model=model_id,
            provider_name=provider_id,
            family=self._family_of(provider_id, model_id),
        )

    def route(
        self,
        agent_type: str,
        problem_type: str = "general",
        complexity: str = "medium",
        time_budget_minutes: int = 5,
        prefer_provider: str | None = None,
    ) -> ModelAssignment:
        """
        Route an agent to the best available model for its role.

        Strategy: first catalog model (in models.yaml order) whose roles
        include the agent type. A requested live provider is honored when
        it offers the role, else its first catalog model is used.
        """
        self._enforce_minimum()

        if prefer_provider and prefer_provider in self._providers:
            spec = self.config.providers[prefer_provider]
            model = next(
                (m for m in spec.models if agent_type in m.roles),
                spec.models[0] if spec.models else None,
            )
            if model is None:
                return self._fallback()
            return ModelAssignment(
                provider=self._providers[prefer_provider],
                model=model.id,
                provider_name=prefer_provider,
                family=model.family,
            )

        candidates = self._candidates(agent_type)
        if candidates:
            provider_id, model_id, family = candidates[0]
            return ModelAssignment(
                provider=self._providers[provider_id],
                model=model_id,
                provider_name=provider_id,
                family=family,
            )
        return self._fallback()

    def route_for_planning(self) -> ModelAssignment:
        """Route specifically for the Planner (cheap classification call)."""
        self._enforce_minimum()
        candidates = self._candidates("planner")
        if candidates:
            provider_id, model_id, family = candidates[0]
            return ModelAssignment(
                provider=self._providers[provider_id],
                model=model_id,
                provider_name=provider_id,
                family=family,
            )
        return self._fallback()
