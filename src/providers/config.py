"""Assembly — models.yaml loader and validation.

Single source of truth for providers, models, families, roles, context
sizes, and rate limits. Fails loudly (FileNotFoundError / ValueError /
pydantic ValidationError) on unknown families, missing fields, a missing
file, or a half-migrated shape — a misconfigured catalog must crash at
startup, never silently route to the wrong model.

Shape (one shape only — no legacy aliases):
  providers.<id>.models[].limits: {rpm, rpd, tpm, context_tokens}
  providers.<id>.models[].scope: "model" | "account"

Each limit accepts an int (>0), the literal "unlimited" (provider
enforces no limit on that field — the limiter skips it), or null
(unknown). Null on any ENABLED provider with models is a startup error:
see validate_limits_filled — fill it from the provider dashboard or set
enabled: false.
"""

from datetime import date, timedelta
from pathlib import Path
from typing import Any, Literal

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


# Quota evidence must be refreshed before a release/demo. Metadata older
# than this window is treated as stale and is never used for routing or
# capacity estimates, even if numeric values remain in the YAML.
QUOTA_METADATA_MAX_AGE_DAYS = 14


class LimitsNotFilledError(ValueError):
    """An enabled model still has null (unknown) limit fields.

    Subclasses ValueError so existing loud-failure handling applies.
    Fill the fields from the provider dashboard (or "unlimited" where
    the provider enforces no limit), or set the provider enabled: false.
    """


# A single limit field: positive int, "unlimited" (not enforced), or
# null (unknown — fails validation for enabled models).
LimitValue = int | Literal["unlimited"] | None


def _valid_limit(value: LimitValue, field: str) -> LimitValue:
    if value is None or value == "unlimited":
        return value
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise ValueError(
            f"{field} must be a positive int, 'unlimited', or null; got {value!r}"
        )
    return value


class ModelLimits(BaseModel):
    """Per-model rate limits. rpm/rpd/tpm/context_tokens must be filled
    (int or "unlimited") for models on enabled providers; tpd is optional
    (absent/null/"unlimited" = not enforced, never fails validation)."""

    model_config = ConfigDict(extra="forbid")

    rpm: LimitValue = Field(default=None, description="Requests per minute")
    rpd: LimitValue = Field(default=None, description="Requests per day")
    tpm: LimitValue = Field(default=None, description="Tokens per minute")
    tpd: LimitValue = Field(default=None, description="Tokens per day (optional)")
    context_tokens: LimitValue = Field(default=None, description="Context window")

    @field_validator("rpm", "rpd", "tpm", "tpd", "context_tokens")
    @classmethod
    def _valid_fields(cls, value: LimitValue, info: Any) -> LimitValue:
        return _valid_limit(value, str(info.field_name))


class ModelSpec(BaseModel):
    """One routable model and what it may be used for."""

    model_config = ConfigDict(extra="forbid")

    id: str = Field(min_length=1)
    family: str = Field(min_length=1)
    roles: list[str] = Field(min_length=1)
    scope: Literal["model", "account"] = Field(
        default="model",
        description="'model': limits enforced per (key, model); "
        "'account': limits shared across the provider's models on one key",
    )
    limits: ModelLimits = Field(default_factory=ModelLimits)

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
    privacy_note: str | None = Field(
        default=None,
        description="Optional free-tier data-use notice shown in the privacy dialog.",
    )
    key_steps: list[str] | None = Field(
        default=None,
        description="Generic safe key-setup steps shown in the setup stepper.",
    )
    key_notes: list[str] | None = Field(
        default=None,
        description="Optional extra setup notes shown below the stepper.",
    )
    sensitive_signup: str | None = Field(
        default=None,
        description="Provider-specific signup fact or null when unconfirmed.",
    )
    models: list[ModelSpec] = Field(default_factory=list)
    quota_source: str | None = Field(
        default=None,
        description="Authoritative URL or dashboard location for quota evidence.",
    )
    quota_last_verified: date | None = Field(
        default=None,
        description="Date the provider quota fields were checked against the source.",
    )

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

    def model_spec(self, provider_id: str, model_id: str) -> ModelSpec:
        """Look up one catalog model. Raises KeyError on unknown ids."""
        try:
            spec = self.providers[provider_id]
        except KeyError:
            raise KeyError(
                f"unknown provider {provider_id!r}; "
                f"available: {sorted(self.providers)} (see models.yaml)"
            ) from None
        for model in spec.models:
            if model.id == model_id:
                return model
        raise KeyError(
            f"unknown model {model_id!r} for provider {provider_id!r}; "
            f"available: {[m.id for m in spec.models]} (see models.yaml)"
        )

    def limits_of(self, provider_id: str, model_id: str) -> ModelLimits:
        """Effective limits for one model (per-model — no fallback)."""
        return self.model_spec(provider_id, model_id).limits

    def scope_of(self, provider_id: str, model_id: str) -> str:
        """'model' or 'account': which bucket enforces this model's limits."""
        return self.model_spec(provider_id, model_id).scope


def quota_metadata_issue(
    provider_id: str,
    spec: ProviderSpec,
    *,
    today: date | None = None,
    max_age_days: int = QUOTA_METADATA_MAX_AGE_DAYS,
) -> str | None:
    """Return why enabled provider quota metadata is not safe to plan with.

    Metadata is valid only when a source URL/location and verification date
    are present, recent, and not in the future, and required quota fields are
    filled for every model. Disabled providers are intentionally not gated.
    """
    if not spec.enabled or not spec.models:
        return None
    current_date = today or date.today()
    if not spec.quota_source or not spec.quota_source.strip():
        return f"QUOTA METADATA MISSING for provider {provider_id!r}: add quota_source"
    if spec.quota_last_verified is None:
        return f"QUOTA METADATA MISSING for provider {provider_id!r}: add quota_last_verified"
    if spec.quota_last_verified > current_date:
        return (
            f"QUOTA METADATA INVALID for provider {provider_id!r}: "
            "quota_last_verified is in the future"
        )
    expires_on = spec.quota_last_verified + timedelta(days=max_age_days)
    if current_date > expires_on:
        return (
            f"QUOTA METADATA STALE for provider {provider_id!r}: verified "
            f"{spec.quota_last_verified.isoformat()}, maximum age {max_age_days} days; "
            "recheck the provider dashboard before routing"
        )
    problems: list[str] = []
    for model in spec.models:
        missing = [
            field
            for field in ("rpm", "rpd", "tpm", "context_tokens")
            if getattr(model.limits, field) is None
        ]
        if missing:
            problems.append(f"{model.id}: {', '.join(missing)}")
    if problems:
        return (
            f"LIMITS NOT FILLED for enabled provider {provider_id!r} "
            "(fill from the dashboard or set enabled: false): " + "; ".join(problems)
        )
    return None


def validate_provider_limits(
    provider_id: str,
    spec: ProviderSpec,
    *,
    today: date | None = None,
    max_age_days: int = QUOTA_METADATA_MAX_AGE_DAYS,
) -> None:
    """Raise LimitsNotFilledError unless quota metadata is complete and fresh."""
    issue = quota_metadata_issue(
        provider_id, spec, today=today, max_age_days=max_age_days
    )
    if issue:
        raise LimitsNotFilledError(issue)



def provider_limits_issue(
    provider_id: str,
    spec: ProviderSpec,
    *,
    today: date | None = None,
    max_age_days: int = QUOTA_METADATA_MAX_AGE_DAYS,
) -> str | None:
    """Return a safe, actionable reason a provider cannot be routed.

    Provider limit gaps are a capability/readiness issue, not a reason to
    crash the whole API. The router and catalog use this shared policy so
    a provider is never advertised as runnable while its limits are unknown.
    """
    try:
        validate_provider_limits(
            provider_id, spec, today=today, max_age_days=max_age_days
        )
    except LimitsNotFilledError as exc:
        return str(exc)
    return None


def validate_limits_filled(config: ModelsConfig) -> None:
    """Raise LimitsNotFilledError if any enabled provider has null limits."""
    for provider_id, spec in config.providers.items():
        validate_provider_limits(provider_id, spec)


import sys


def default_catalog_path() -> Path:
    """Repo-root models.yaml (or PyInstaller bundle root)."""
    if getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS"):
        return Path(sys._MEIPASS) / "models.yaml"
    return Path(__file__).resolve().parent.parent.parent / "models.yaml"


def load_models_config(path: str | Path | None = None) -> ModelsConfig:
    """Load and validate the catalog. Raises loudly on any problem."""
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
    if not isinstance(raw, dict):
        raise TypeError(
            f"models.yaml at {catalog} must contain a mapping at the top level"
        )
    return ModelsConfig.model_validate(raw)
