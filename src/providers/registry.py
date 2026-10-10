"""
Assembly — provider registry: get_provider(provider_id, api_key).

Builds provider instances from models.yaml. Unknown ids, disabled
providers, and unknown backends fail loudly. Server-key wiring lives in
the router; user-supplied (BYOK) keys flow straight through here and are
never persisted — the registry holds the key only on the instance.
"""

from pathlib import Path

from pydantic import SecretStr

from src.core.keystore import clean_key
from src.providers.base import AIProvider
from src.providers.config import ModelsConfig, load_models_config
from src.providers.gemini_provider import GeminiProvider
from src.providers.huggingface_provider import HuggingFaceProvider
from src.providers.openai_compat import OpenAICompatibleProvider


class ProviderDisabledError(ValueError):
    """Raised when a provider is disabled in models.yaml (opt-in only)."""


def get_provider(
    provider_id: str,
    api_key: str | SecretStr,
    config: ModelsConfig | None = None,
    models_yaml: str | Path | None = None,
) -> AIProvider:
    """Construct the provider for id, authenticated with api_key."""
    catalog = config or load_models_config(models_yaml)
    key = clean_key(api_key)
    if provider_id not in catalog.providers:
        raise KeyError(
            f"unknown provider {provider_id!r}; "
            f"available: {sorted(catalog.providers)} (see models.yaml)"
        )
    spec = catalog.providers[provider_id]
    if not spec.enabled:
        raise ProviderDisabledError(
            f"provider {provider_id!r} is disabled in models.yaml "
            "(set enabled: true to opt in)"
        )
    if spec.base == "openai-compatible":
        if not spec.url:
            raise ValueError(
                f"provider {provider_id!r} needs a 'url' for base openai-compatible"
            )
        if not spec.models:
            raise ValueError(
                f"provider {provider_id!r} has no models in models.yaml; "
                "add at least one model with a valid family and roles"
            )
        return OpenAICompatibleProvider(
            provider_id=provider_id,
            api_key=key,
            base_url=spec.url,
            default_model=spec.models[0].id,
            models=[model.id for model in spec.models],
            extra_headers=spec.headers,
            timeout_seconds=spec.timeout_seconds or 60.0,
        )
    if spec.base == "google-genai":
        if not spec.models:
            raise ValueError(f"provider {provider_id!r} has no models in models.yaml")
        return GeminiProvider(
            api_key=key,
            default_model=spec.models[0].id,
            models=[model.id for model in spec.models],
        )
    if spec.base == "huggingface":
        if not spec.models:
            raise ValueError(f"provider {provider_id!r} has no models in models.yaml")
        return HuggingFaceProvider(
            api_key=key,
            default_model=spec.models[0].id,
            models=[model.id for model in spec.models],
        )
    # Unreachable: config validation restricts base to known backends.
    raise ValueError(f"provider {provider_id!r} has unsupported base {spec.base!r}")
