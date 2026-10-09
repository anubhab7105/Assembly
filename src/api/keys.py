"""Assembly — key management API (BYOK, no accounts).

- POST /api/keys/test: one minimal provider call; reports validity
  without ever echoing the key.
- GET /api/providers/status: available providers, model families, and a
  rough capacity estimate for the current APP_MODE key set.
"""

from fastapi import APIRouter, HTTPException, Request, status
from pydantic import BaseModel, ConfigDict, SecretStr

from src.core.config import settings
from src.core.keystore import get_keystore
from src.core.rate_limit import check_rate_limit
from src.providers.base import ChatMessage
from src.providers.config import load_models_config
from src.providers.errors import AuthError, BadResponse, ProviderDown, RateLimited
from src.providers.registry import ProviderDisabledError, get_provider

router = APIRouter(prefix="/api", tags=["keys"])


class KeySaveRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    provider: str
    key: SecretStr


class KeyMaskedResponse(BaseModel):
    provider: str
    masked_key: str


class KeyTestRequest(BaseModel):
    """A key to probe. SecretStr: never serialized, never logged."""

    model_config = ConfigDict(extra="forbid")

    provider: str
    key: SecretStr


class KeyTestResponse(BaseModel):
    provider: str
    valid: bool
    rate_limited: bool
    error_code: str | None = None
    model: str | None = None


class ProviderStatus(BaseModel):
    id: str
    available: bool
    models: list[str]
    families: list[str]
    rpm_remaining: int | None = None
    rpd_remaining: int | None = None
    cooldown_seconds: float = 0.0
    estimated_calls_3min: int | None = None


class ProvidersStatusResponse(BaseModel):
    mode: str
    providers: list[ProviderStatus]
    families: list[str]
    capacity_3min_estimate: int | None = None


@router.post("/keys/test", response_model=KeyTestResponse)
async def test_key(req: KeyTestRequest, request: Request) -> KeyTestResponse:
    """Make one tiny call with the given key; report validity, echo nothing."""
    ip = request.client.host if request.client else "unknown"
    await check_rate_limit(
        f"ip:{ip}", "test_keys", settings.rate_limit_key_test_per_min_per_ip, 60
    )
    try:
        provider = get_provider(req.provider, req.key)
    except (KeyError, ProviderDisabledError, ValueError) as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Unknown or disabled provider: {req.provider}",
        ) from exc

    model = provider.get_available_models()[0] if provider.get_available_models() else ""
    try:
        response = await provider.generate(
            messages=[ChatMessage(role="user", content="Reply with the word ok.")],
            model=model or None,
            temperature=0.0,
            max_tokens=8,
        )
    except RateLimited:
        return KeyTestResponse(
            provider=req.provider, valid=False, rate_limited=True, error_code="rate_limited"
        )
    except AuthError:
        return KeyTestResponse(
            provider=req.provider, valid=False, rate_limited=False, error_code="auth_error"
        )
    except ProviderDown:
        return KeyTestResponse(
            provider=req.provider,
            valid=False,
            rate_limited=False,
            error_code="provider_down",
        )
    except BadResponse:
        return KeyTestResponse(
            provider=req.provider,
            valid=False,
            rate_limited=False,
            error_code="bad_response",
        )
    except Exception:  # noqa: BLE001 — key probe must answer, never 500 or echo
        return KeyTestResponse(
            provider=req.provider, valid=False, rate_limited=False, error_code="error"
        )
    return KeyTestResponse(
        provider=req.provider,
        valid=True,
        rate_limited=False,
        error_code=None,
        model=response.model,
    )


@router.get("/providers/status", response_model=ProvidersStatusResponse)
async def providers_status() -> ProvidersStatusResponse:
    """Available providers, families, and rough capacity for this mode's keys."""
    from src.core.keystore import reveal
    from src.providers.quota import fingerprint_key, get_limiter

    store = get_keystore()
    held = store.get_keys()
    catalog = load_models_config()
    limiter = get_limiter()

    entries: list[ProviderStatus] = []
    families: set[str] = set()
    capacity: int | None = None
    for provider_id, spec in catalog.providers.items():
        available = spec.enabled and provider_id in held
        provider_families = sorted({model.family for model in spec.models})
        entry = ProviderStatus(
            id=provider_id,
            available=available,
            models=[model.id for model in spec.models],
            families=provider_families,
        )
        entries.append(entry)
        if available:
            families.update(provider_families)
            fingerprint = fingerprint_key(reveal(held[provider_id]))
            rpm_left: list[int] = []
            rpd_left: list[int] = []
            worst_cooldown = 0.0
            for model in spec.models:
                remaining = limiter.remaining(provider_id, fingerprint, model.id)
                if remaining["rpm_remaining"] is not None:
                    rpm_left.append(remaining["rpm_remaining"])
                if remaining["rpd_remaining"] is not None:
                    rpd_left.append(remaining["rpd_remaining"])
                worst_cooldown = max(
                    worst_cooldown, float(remaining["cooldown_seconds"] or 0.0)
                )
            entry.rpm_remaining = min(rpm_left) if rpm_left else None
            entry.rpd_remaining = min(rpd_left) if rpd_left else None
            entry.cooldown_seconds = worst_cooldown
            known = [
                value
                for value in (entry.rpm_remaining, entry.rpd_remaining)
                if value is not None
            ]
            if known:
                entry.estimated_calls_3min = min(known)
                capacity = (capacity or 0) + entry.estimated_calls_3min

    return ProvidersStatusResponse(
        mode=settings.app_mode,
        providers=entries,
        families=sorted(families),
        capacity_3min_estimate=capacity,
    )


@router.post("/keys", response_model=KeyMaskedResponse)
async def save_key(req: KeySaveRequest):
    if settings.app_mode != "desktop":
        raise HTTPException(
            status_code=400, detail="Key saving is only supported in desktop mode"
        )
    store = get_keystore()
    store.set_key(req.provider, req.key)
    return KeyMaskedResponse(provider=req.provider, masked_key="***")


@router.get("/keys", response_model=list[KeyMaskedResponse])
async def list_keys():
    if settings.app_mode != "desktop":
        raise HTTPException(
            status_code=400, detail="Key listing is only supported in desktop mode"
        )
    store = get_keystore()
    keys = store.get_keys()
    return [KeyMaskedResponse(provider=p, masked_key="***") for p in keys]


@router.delete("/keys/{provider}")
async def delete_key(provider: str):
    if settings.app_mode != "desktop":
        raise HTTPException(
            status_code=400, detail="Key deletion is only supported in desktop mode"
        )
    store = get_keystore()
    if hasattr(store, "delete"):
        store.delete(provider)
    else:
        store.set_key(provider, None)
    return {"detail": "Key deleted"}


@router.delete("/keys")
async def delete_all_keys():
    """Clear every key from the local keyring. Keys persist until this is called."""
    if settings.app_mode != "desktop":
        raise HTTPException(
            status_code=400, detail="Key deletion is only supported in desktop mode"
        )
    store = get_keystore()
    store.clear()
    return {"detail": "All keys deleted"}
