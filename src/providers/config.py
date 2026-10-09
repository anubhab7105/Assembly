"""
Assembly — models.yaml loader and validation.

Single source of truth for providers, models, families, roles, context
sizes, and rate limits. Fails loudly (FileNotFoundError / ValueError /
pydantic ValidationError) on unknown families, missing fields, or a
missing file — a misconfigured catalog must crash at startup, never
silently route to the wrong model.
"""

from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, ConfigDict, Field, field_validator

# Model families the independence accounting understands. Two providers
# serving the same family are NOT independent (see docs/TECH_STACK.md).
# Add a new family here deliberately when a new model lineage appears —
# never silently accept an unclassified one.
KNOWN_FAMILIES = frozenset(
    {
        "gemini",
        "llama",
        "qwen",
        "gpt-oss",
        "deepseek",
        "mistral",
        "kimi",
        "gemma",
        "nemotron",
        "allam",
        "phi",
    }
)

# Agent roles the router may assign.
KNOWN_ROLES = frozenset({"solver", "researcher", "critic", "synthesizer", "planner"})

# Provider backends the registry knows how to construct.
KNOWN_BASES = frozenset({"openai-compatible", "google-genai", "huggingface"})


class ModelLimits(BaseModel):
    """Rate limits per provider key. All optional until filled from dashboards."""

    model_config = ConfigDict(extra="forbid")

    rpm: int | None = Field(default=None, description="Requests per minute")
    rpd: int | None = Field(default=None, description="Requests per day")
    tpm: int | None = Field(default=None, description="Tokens per minute")


class ModelSpec(BaseModel):
    """One routable model and what it may be used for."""

    model_config = ConfigDict(extra="forbid")

    id: str = Field(min_length=1)
    family: str = Field(min_length=1)
    roles: list[str] = Field(min_length=1)
    context_tokens: int | None = Field(default=None, gt=0)

    @field_validator("family")
    @classmethod
    def _known_family(cls, value: str) -> str:
        if value not in KNOWN_FAMILIES:
            raise ValueError(
                f"unknown model family {value!r}; must be one of {sorted(KNOWN_FAMILIES)}"
            )
        return value

    @field_validator("roles")
    @classmethod
    def _known_roles(cls, value: list[str]) -> list[str]:
        unknown = [role for role in value if role not in KNOWN_ROLES]
        if unknown:
            raise ValueError(
                f"unknown roles {unknown}; must be a subset of {sorted(KNOWN_ROLES)}"
            )
        return value


class ProviderSpec(BaseModel):
    """One provider entry: how to reach it and what it offers."""

    model_config = ConfigDict(extra="forbid")

    base: str
    url: str | None = None
    key_url: str = ""
    enabled: bool = True
    headers: dict[str, str] = Field(default_factory=dict)
    timeout_seconds: float | None = Field(default=None, gt=0)
    models: list[ModelSpec] = Field(default_factory=list)
    limits: ModelLimits = Field(default_factory=ModelLimits)

    @field_validator("base")
    @classmethod
    def _known_base(cls, value: str) -> str:
        if value not in KNOWN_BASES:
            raise ValueError(
                f"unknown provider base {value!r}; must be one of {sorted(KNOWN_BASES)}"
            )
        return value


class ModelsConfig(BaseModel):
    """The whole catalog: provider id → spec. Order is routing priority."""

    model_config = ConfigDict(extra="forbid")

    providers: dict[str, ProviderSpec] = Field(min_length=1)


import sys


def default_catalog_path() -> Path:
    """Repo-root models.yaml (or PyInstaller bundle root)."""
    if getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS"):
        return Path(sys._MEIPASS) / "models.yaml"
    return Path(__file__).resolve().parent.parent.parent / "models.yaml"


DEFAULT_RPM = 15
DEFAULT_RPD = 200
DEFAULT_TPM = 40000
DEFAULT_CONTEXT = 8192

def load_models_config(path: str | Path | None = None) -> ModelsConfig:
    """Load and validate the catalog. Raises loudly on any problem."""
    from src.core.logging_config import logger
    
    catalog = Path(path) if path else default_catalog_path()
    if not catalog.is_file():
        raise FileNotFoundError(
            f"models.yaml not found at {catalog}; copy docs/TECH_STACK.md section 3.5 "
            "into models.yaml at the repo root"
        )
    try:
        raw: Any = yaml.safe_load(catalog.read_text(encoding="utf-8"))
    except yaml.YAMLError as exc:
        raise ValueError(f"models.yaml at {catalog} is not valid YAML: {exc}") from exc
    if not isinstance(raw, dict) or "providers" not in raw:
        raise TypeError(
            f"models.yaml at {catalog} must contain a 'providers' mapping at the top level"
        )
    
    # Apply conservative defaults for null limits and context sizes, emitting warnings
    for provider_name, provider_data in raw["providers"].items():
        limits = provider_data.get("limits", {})
        if limits:
            if limits.get("rpm") is None:
                logger.warning(f"Config  │ {provider_name} has null rpm limit; defaulting to {DEFAULT_RPM}")
                limits["rpm"] = DEFAULT_RPM
            if limits.get("rpd") is None:
                logger.warning(f"Config  │ {provider_name} has null rpd limit; defaulting to {DEFAULT_RPD}")
                limits["rpd"] = DEFAULT_RPD
            if limits.get("tpm") is None:
                logger.warning(f"Config  │ {provider_name} has null tpm limit; defaulting to {DEFAULT_TPM}")
                limits["tpm"] = DEFAULT_TPM
            provider_data["limits"] = limits
            
        models = provider_data.get("models", [])
        for model in models:
            if model.get("context_tokens") is None:
                logger.warning(f"Config  │ {provider_name} model {model.get('id')} has null context_tokens; defaulting to {DEFAULT_CONTEXT}")
                model["context_tokens"] = DEFAULT_CONTEXT

    return ModelsConfig.model_validate(raw)
