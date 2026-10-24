"""Assembly — model catalog (GET /api/catalog from models.yaml)."""

from fastapi import APIRouter
from pydantic import BaseModel, ConfigDict

from src.providers.config import QUOTA_METADATA_MAX_AGE_DAYS, load_models_config, provider_limits_issue

router = APIRouter(prefix="/api/catalog", tags=["catalog"])

#: Shown in the setup UI whenever a provider-specific signup fact is
#: unconfirmed (sensitive_signup is null). Free-tier only: never suggest
#: paying for a key.
SENSITIVE_SIGNUP_FALLBACK = (
    "Check this during signup; if it asks for payment, "
    "skip this provider (Assembly is free-tier only)"
)

#: Minimum distinct model families for a healthy team (2 works with warning).
MIN_FAMILIES_TO_START = 3


class CatalogModel(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    family: str
    roles: list[str]
    scope: str


class CatalogProvider(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    enabled: bool
    limits_ready: bool
    limits_issue: str | None = None
    quota_source: str | None = None
    quota_last_verified: str | None = None
    quota_stale_after_days: int = QUOTA_METADATA_MAX_AGE_DAYS
    key_url: str = ""
    privacy_note: str | None = None
    key_steps: list[str] | None = None
    key_notes: list[str] | None = None
    sensitive_signup: str | None = None
    models: list[CatalogModel]


class CatalogResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    providers: list[CatalogProvider]
    families: list[str]
    recommended_order: list[str] = []
    minimum_families: int = MIN_FAMILIES_TO_START
    sensitive_signup_fallback: str = SENSITIVE_SIGNUP_FALLBACK


def recommended_provider_order(catalog: object) -> list[str]:
    """Enabled providers, most capacity first (names only, never keys).

    Score = sum of integer rpd + rpm/10 across models; unknown limits
    score 0 so unfilled providers sort last. Pure helper for the setup
    banner's recommended order.
    """
    scored: list[tuple[float, str]] = []
    providers = getattr(catalog, "providers", {}) or {}
    for pid, spec in providers.items():
        if not getattr(spec, "enabled", False):
            continue
        if provider_limits_issue(str(pid), spec) is not None:
            continue
        total = 0.0
        for model in getattr(spec, "models", []) or []:
            limits = getattr(model, "limits", None)
            if limits is None:
                continue
            rpd = getattr(limits, "rpd", None)
            rpm = getattr(limits, "rpm", None)
            if isinstance(rpd, int) and not isinstance(rpd, bool):
                total += float(rpd)
            if isinstance(rpm, int) and not isinstance(rpm, bool):
                total += float(rpm) / 10.0
        scored.append((total, str(pid)))
    scored.sort(key=lambda item: (-item[0], item[1]))
    return [pid for _, pid in scored]


@router.get("", response_model=CatalogResponse)
def get_catalog() -> CatalogResponse:
    """Providers, models and families from models.yaml (no keys)."""
    catalog = load_models_config()
    providers: list[CatalogProvider] = []
    families: set[str] = set()
    for pid, spec in catalog.providers.items():
        limits_issue = provider_limits_issue(pid, spec) if spec.enabled else None
        limits_ready = spec.enabled and limits_issue is None
        models = [
            CatalogModel(id=m.id, family=m.family, roles=list(m.roles), scope=m.scope)
            for m in spec.models
        ]
        providers.append(
            CatalogProvider(
                id=pid,
                enabled=spec.enabled,
                limits_ready=limits_ready,
                limits_issue=limits_issue,
                quota_source=spec.quota_source,
                quota_last_verified=(
                    spec.quota_last_verified.isoformat()
                    if spec.quota_last_verified
                    else None
                ),
                quota_stale_after_days=QUOTA_METADATA_MAX_AGE_DAYS,
                key_url=spec.key_url,
                privacy_note=spec.privacy_note,
                key_steps=list(spec.key_steps) if spec.key_steps else None,
                key_notes=list(spec.key_notes) if spec.key_notes else None,
                sensitive_signup=spec.sensitive_signup,
                models=models,
            )
        )
        if limits_ready:
            families.update(m.family for m in spec.models)
    return CatalogResponse(
        providers=providers,
        families=sorted(families),
        recommended_order=recommended_provider_order(catalog),
        minimum_families=MIN_FAMILIES_TO_START,
        sensitive_signup_fallback=SENSITIVE_SIGNUP_FALLBACK,
    )
