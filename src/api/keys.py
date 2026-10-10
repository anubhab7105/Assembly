"""Assembly — key management API (BYOK, no accounts).

- POST /api/keys/test: one auth-only models-list call; reports key
  validity without ever echoing the key. Only an authentication
  failure reports "invalid"; quota, model-availability, and
  transport problems each report their own state.
- GET /api/providers/status: available providers, model families, and a
  rough capacity estimate for the current APP_MODE key set.
"""

import httpx
from fastapi import APIRouter, HTTPException, Request, status
from pydantic import BaseModel, ConfigDict, SecretStr

from src.core.config import settings
from src.core.keystore import clean_key, get_keystore
from src.core.rate_limit import check_rate_limit, client_ip
from src.providers.config import load_models_config
from src.providers.router import DiversityGateResponse

router = APIRouter(prefix="/api", tags=["keys"])

#: Auth-only list endpoints (no generation, no quota-lease side effects).
_GEMINI_LIST_URL = "https://generativelanguage.googleapis.com/v1beta/models"
_HF_MODEL_URL = "https://huggingface.co/api/models/{model}"

#: List probe budget: auth answers fast; anything slower is reported as
#: unreachable instead of hanging the setup UI (the old generation probe
#: took 45-120 s and timed out the page).
_LIST_TIMEOUT_SECONDS = 15.0

_COPY_HINT = "Check the key was copied without spaces."


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
    #: Plain-language reason for the UI (never contains key material).
    message: str | None = None
    #: Key validity vs model availability are reported separately: valid
    #: answers "does Google accept this key", model_available answers
    #: "can this key use the configured model".
    model_available: bool | None = None
    #: Model ids the key can use (set when the configured model is
    #: unavailable but the key is valid).
    available_models: list[str] | None = None


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
    diversity: DiversityGateResponse = DiversityGateResponse()


@router.post("/keys/test", response_model=KeyTestResponse)
async def test_key(req: KeyTestRequest, request: Request) -> KeyTestResponse:
    """Validate a key with one auth-only models-list call; echo nothing."""
    ip = client_ip(request)
    await check_rate_limit(
        f"ip:{ip}", "test_keys", settings.rate_limit_key_test_per_min_per_ip, 60
    )
    key = clean_key(req.key)
    if not key:
        return KeyTestResponse(
            provider=req.provider,
            valid=False,
            rate_limited=False,
            error_code="auth_error",
            message=f"No key entered. {_COPY_HINT}",
        )
    try:
        catalog = load_models_config()
    except (FileNotFoundError, ValueError, TypeError):
        return KeyTestResponse(
            provider=req.provider,
            valid=False,
            rate_limited=False,
            error_code="error",
            message="Server catalog is unavailable; try again.",
        )
    spec = catalog.providers.get(req.provider)
    if spec is None or not spec.enabled:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Unknown or disabled provider: {req.provider}",
        )
    model = spec.models[0].id if spec.models else ""
    label = "Google" if spec.base == "google-genai" else req.provider
    if spec.base == "google-genai":
        list_status, listed, list_body = await _list_gemini(key)
    elif spec.base == "openai-compatible":
        list_status, listed, list_body = await _list_openai(
            spec.url or "", key, dict(spec.headers)
        )
    elif spec.base == "huggingface":
        return await _test_huggingface(req.provider, model, key)
    else:  # Unreachable: config validation restricts base to known backends.
        return KeyTestResponse(
            provider=req.provider,
            valid=False,
            rate_limited=False,
            error_code="error",
            message="Server catalog is unavailable; try again.",
        )
    return _classify_list_result(
        req.provider, label, model, list_status, listed, list_body
    )


async def _list_gemini(key: str) -> tuple[int | None, list[str], str]:
    """GET the Gemini catalog with header auth (key never in the URL).

    Returns (http status or None on transport failure, model ids, body).
    One call, no retries by design.
    """
    try:
        async with httpx.AsyncClient(timeout=_LIST_TIMEOUT_SECONDS) as client:
            response = await client.get(
                _GEMINI_LIST_URL,
                headers={"x-goog-api-key": key, "Content-Type": "application/json"},
            )
    except Exception:  # noqa: BLE001 — any transport failure reads as unreachable
        return None, [], ""
    if response.status_code != 200:
        return response.status_code, [], response.text[:500]
    try:
        data = response.json()
    except ValueError:
        return response.status_code, [], ""
    models = data.get("models", []) if isinstance(data, dict) else []
    ids = sorted(
        str(item.get("name", "")).replace("models/", "")
        for item in models
        if isinstance(item, dict) and item.get("name")
    )
    return response.status_code, ids, ""


async def _list_openai(
    base_url: str, key: str, extra_headers: dict[str, str]
) -> tuple[int | None, list[str], str]:
    """GET {base}/models once. Returns (status|None, ids, body)."""
    try:
        async with httpx.AsyncClient(timeout=_LIST_TIMEOUT_SECONDS) as client:
            response = await client.get(
                base_url.rstrip("/") + "/models",
                headers={"Authorization": f"Bearer {key}", **extra_headers},
            )
    except Exception:  # noqa: BLE001 — any transport failure reads as unreachable
        return None, [], ""
    if response.status_code != 200:
        return response.status_code, [], response.text[:500]
    try:
        data = response.json()
    except ValueError:
        return response.status_code, [], ""
    ids = sorted(
        str(item.get("id", ""))
        for item in (data.get("data", []) if isinstance(data, dict) else [])
        if isinstance(item, dict) and item.get("id")
    )
    return response.status_code, ids, ""


async def _test_huggingface(provider: str, model: str, key: str) -> KeyTestResponse:
    """HuggingFace has no key-scoped list endpoint: probe model existence."""
    try:
        async with httpx.AsyncClient(timeout=_LIST_TIMEOUT_SECONDS) as client:
            response = await client.get(
                _HF_MODEL_URL.format(model=model),
                headers={"Authorization": f"Bearer {key}"},
            )
    except Exception:  # noqa: BLE001 — any transport failure reads as unreachable
        return KeyTestResponse(
            provider=provider,
            valid=False,
            rate_limited=False,
            error_code="unreachable",
            model=model or None,
            model_available=None,
            message="Couldn't reach Hugging Face; try again.",
        )
    if response.status_code == 200:
        return KeyTestResponse(
            provider=provider,
            valid=True,
            rate_limited=False,
            error_code=None,
            model=model or None,
            model_available=True,
            message=f"Key verified for {provider}.",
        )
    if response.status_code in (401, 403):
        return KeyTestResponse(
            provider=provider,
            valid=False,
            rate_limited=False,
            error_code="auth_error",
            model=model or None,
            model_available=None,
            message=f"Key was rejected by {provider}. {_COPY_HINT}",
        )
    if response.status_code == 429:
        return KeyTestResponse(
            provider=provider,
            valid=False,
            rate_limited=True,
            error_code="rate_limited",
            model=model or None,
            model_available=None,
            message="Key is valid; quota or rate limit reached right now. Try again in a minute.",
        )
    if response.status_code == 404:
        return KeyTestResponse(
            provider=provider,
            valid=True,
            rate_limited=False,
            error_code="model_not_found",
            model=model or None,
            model_available=False,
            available_models=[],
            message=f"Key is valid; model {model} is not available to this key.",
        )
    return KeyTestResponse(
        provider=provider,
        valid=False,
        rate_limited=False,
        error_code="unreachable",
        model=model or None,
        model_available=None,
        message=f"Couldn't reach {provider}; try again.",
    )


def _classify_list_result(
    provider: str,
    label: str,
    model: str,
    list_status: int | None,
    listed: list[str],
    list_body: str,
) -> KeyTestResponse:
    """Classify by status code only. Only an auth failure is 'invalid'."""
    if list_status is None:
        return KeyTestResponse(
            provider=provider,
            valid=False,
            rate_limited=False,
            error_code="unreachable",
            model=model or None,
            model_available=None,
            message=f"Couldn't reach {label}; try again.",
        )
    if list_status == 200:
        if model and model not in listed:
            return KeyTestResponse(
                provider=provider,
                valid=True,
                rate_limited=False,
                error_code="model_not_found",
                model=model,
                model_available=False,
                available_models=listed,
                message=f"Key is valid; model {model} is not available to this key.",
            )
        return KeyTestResponse(
            provider=provider,
            valid=True,
            rate_limited=False,
            error_code=None,
            model=model or None,
            model_available=True if model else None,
            message=f"Key verified for {provider}.",
        )
    lowered = (list_body or "").lower()
    if list_status in (401, 403) or (
        list_status == 400 and "api_key_invalid" in lowered
    ):
        return KeyTestResponse(
            provider=provider,
            valid=False,
            rate_limited=False,
            error_code="auth_error",
            model=model or None,
            model_available=None,
            message=f"Key was rejected by {label}. {_COPY_HINT}",
        )
    if list_status == 429:
        return KeyTestResponse(
            provider=provider,
            valid=False,
            rate_limited=True,
            error_code="rate_limited",
            model=model or None,
            model_available=None,
            message="Key is valid; quota or rate limit reached right now. Try again in a minute.",
        )
    if list_status == 404:
        return KeyTestResponse(
            provider=provider,
            valid=True,
            rate_limited=False,
            error_code="model_not_found",
            model=model or None,
            model_available=False,
            available_models=listed,
            message=f"Key is valid; model {model} is not available to this key.",
        )
    if list_status == 400:
        return KeyTestResponse(
            provider=provider,
            valid=False,
            rate_limited=False,
            error_code="bad_response",
            model=model or None,
            model_available=None,
            message=f"{label} refused the request; try again.",
        )
    return KeyTestResponse(
        provider=provider,
        valid=False,
        rate_limited=False,
        error_code="unreachable",
        model=model or None,
        model_available=None,
        message=f"Couldn't reach {label}; try again.",
    )


def _diversity_for_keys(held: object) -> DiversityGateResponse:
    """Family gate for this mode's key set. Fail-open to BLOCKED."""
    try:
        from src.core.keystore import reveal
        from src.providers.router import ModelRouter

        raw = held if isinstance(held, dict) else {}
        revealed = {p: reveal(k) for p, k in raw.items() if reveal(k)}
        gate = ModelRouter(keys=revealed).diversity_gate()
        return DiversityGateResponse(**gate.to_dict())  # type: ignore[arg-type]
    except Exception:  # noqa: BLE001 — status must answer, never 500
        return DiversityGateResponse()


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
        diversity=_diversity_for_keys(held),
    )


@router.post("/keys", response_model=KeyMaskedResponse)
async def save_key(req: KeySaveRequest):
    if settings.app_mode != "desktop":
        raise HTTPException(
            status_code=400, detail="Key saving is only supported in desktop mode"
        )
    store = get_keystore()
    store.set_key(req.provider, clean_key(req.key))
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
