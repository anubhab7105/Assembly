"""Assembly — key management API (BYOK, no accounts).

- POST /api/keys/test: one auth-only models-list call; reports key
  validity without ever echoing the key. Only an authentication
  failure reports "invalid"; quota, model-availability, and
  transport problems each report their own state.
- GET /api/providers/status: available providers, model families, and a
  rough capacity estimate for the current APP_MODE key set.
"""

from datetime import UTC, datetime

import httpx
from fastapi import APIRouter, HTTPException, Request, status
from pydantic import BaseModel, ConfigDict, SecretStr

from src.core.config import settings
from src.core.keystore import clean_key, get_keystore
from src.core.rate_limit import check_rate_limit, client_ip
from src.providers.config import load_models_config, provider_limits_issue
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


class VerifiedModelMetadata(BaseModel):
    id: str
    available: bool | None
    context_tokens: int | None = None
    output_tokens: int | None = None


class ObservedQuota(BaseModel):
    field: str
    value: int
    unit: str
    scope: str
    source: str


class KeyMetadataVerification(BaseModel):
    checked_at: str
    provider_enabled: bool
    model_catalog_checked: bool
    models: list[VerifiedModelMetadata]
    observed_quotas: list[ObservedQuota]
    unverified_fields: list[str]
    quota_metadata_ready: bool
    quota_metadata_issue: str | None = None
    note: str


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
    verification: KeyMetadataVerification | None = None


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
    if spec is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Unknown provider: {req.provider}",
        )
    model = spec.models[0].id if spec.models else ""
    label = "Google" if spec.base == "google-genai" else req.provider
    model_metadata: dict[str, dict[str, int]] = {}
    quota_headers: dict[str, str] = {}
    openrouter_key_info: dict[str, int] = {}
    if spec.base == "google-genai":
        list_status, listed, invalid_key_signal, model_metadata = await _list_gemini(key)
    elif spec.base == "openai-compatible":
        list_status, listed, invalid_key_signal, model_metadata, quota_headers = await _list_openai(
            spec.url or "", key, dict(spec.headers)
        )
        if req.provider == "openrouter" and list_status == 200:
            openrouter_key_info = await _openrouter_key_info(key)
    elif spec.base == "huggingface":
        result = await _test_huggingface(req.provider, model, key)
        if result.valid:
            model_availability: dict[str, bool | None] = {model: result.model_available}
            for configured in spec.models[1:]:
                probe = await _test_huggingface(req.provider, configured.id, key)
                model_availability[configured.id] = (
                    probe.model_available if probe.valid or probe.error_code == "model_not_found" else None
                )
            available_models = [
                model_id for model_id, available in model_availability.items() if available is True
            ]
            result.available_models = available_models
            result.verification = _build_key_metadata_verification(
                req.provider, spec, available_models, {}, {}, {},
                model_availability=model_availability,
            )
        if not spec.enabled and result.valid:
            result.message = (
                f"Key verified; {req.provider} is still disabled in models.yaml "
                "and will not be used for runs."
            )
        return result
    else:  # Unreachable: config validation restricts base to known backends.
        return KeyTestResponse(
            provider=req.provider,
            valid=False,
            rate_limited=False,
            error_code="error",
            message="Server catalog is unavailable; try again.",
        )

    result = _classify_list_result(
        req.provider, label, model, list_status, listed, invalid_key_signal
    )
    if list_status == 200:
        result.verification = _build_key_metadata_verification(
            req.provider, spec, listed, model_metadata, quota_headers, openrouter_key_info
        )
    if not spec.enabled and result.valid:
        result.message = (
            f"Key verified; {req.provider} is still disabled in models.yaml "
            "and will not be used for runs."
        )
    return result


async def _list_gemini(
    key: str,
) -> tuple[int | None, list[str], bool, dict[str, dict[str, int]]]:
    """List Gemini models and retain documented per-model token limits.

    API-key authentication stays in the header. This is a read-only catalogue
    request: it does not consume generation quota or verify project rate limits.
    """
    try:
        async with httpx.AsyncClient(timeout=_LIST_TIMEOUT_SECONDS) as client:
            response = await client.get(
                _GEMINI_LIST_URL,
                headers={"x-goog-api-key": key, "Content-Type": "application/json"},
            )
    except Exception:  # noqa: BLE001 — any transport failure reads as unreachable
        return None, [], False, {}
    if response.status_code != 200:
        invalid_key_signal = (
            _provider_invalid_key_signal(response)
            if response.status_code == 400
            else False
        )
        return response.status_code, [], invalid_key_signal, {}
    try:
        data = response.json()
    except ValueError:
        return response.status_code, [], False, {}
    models = data.get("models", []) if isinstance(data, dict) else []
    ids: list[str] = []
    metadata: dict[str, dict[str, int]] = {}
    for item in models:
        if not isinstance(item, dict) or not item.get("name"):
            continue
        model_id = str(item["name"]).removeprefix("models/")
        ids.append(model_id)
        limits: dict[str, int] = {}
        for source, target in (
            ("inputTokenLimit", "context_tokens"),
            ("outputTokenLimit", "output_tokens"),
        ):
            value = _positive_int(item.get(source))
            if value is not None:
                limits[target] = value
        if limits:
            metadata[model_id] = limits
    return response.status_code, sorted(ids), False, metadata


def _provider_invalid_key_signal(response: httpx.Response) -> bool:
    """Extract an invalid-key marker without retaining provider diagnostics."""
    try:
        payload = response.json()
    except ValueError:
        return False
    error = payload.get("error") if isinstance(payload, dict) else None
    if not isinstance(error, dict):
        return False

    # Google uses API_KEY_INVALID in ErrorInfo details[].reason; some
    # OpenAI-compatible APIs use invalid_api_key in top-level code fields.
    # Google may put API_KEY_INVALID in details[].reason. Avoid retaining or
    # scanning free-form provider messages and discard the payload.
    candidates = [error.get(field) for field in ("code", "status")]
    details = error.get("details")
    if isinstance(details, list):
        candidates.extend(
            detail.get("reason")
            for detail in details
            if isinstance(detail, dict)
        )

    for value in candidates:
        if not isinstance(value, str):
            continue
        normalized = value.lower().replace("-", "_").replace(" ", "_")
        if "api_key_invalid" in normalized or "invalid_api_key" in normalized:
            return True
    return False


async def _list_openai(
    base_url: str, key: str, extra_headers: dict[str, str]
) -> tuple[int | None, list[str], bool, dict[str, dict[str, int]], dict[str, str]]:
    """GET {base}/models once; retain only safe, allowlisted metadata."""
    try:
        async with httpx.AsyncClient(timeout=_LIST_TIMEOUT_SECONDS) as client:
            response = await client.get(
                base_url.rstrip("/") + "/models",
                headers={"Authorization": f"Bearer {key}", **extra_headers},
            )
    except Exception:  # noqa: BLE001 — any transport failure reads as unreachable
        return None, [], False, {}, {}
    if response.status_code != 200:
        invalid_key_signal = (
            _provider_invalid_key_signal(response) if response.status_code == 400 else False
        )
        return response.status_code, [], invalid_key_signal, {}, {}
    try:
        data = response.json()
    except ValueError:
        return response.status_code, [], False, {}, {}
    items = data.get("data", []) if isinstance(data, dict) else []
    ids: list[str] = []
    metadata: dict[str, dict[str, int]] = {}
    for item in items:
        if not isinstance(item, dict) or not item.get("id"):
            continue
        model_id = str(item["id"])
        ids.append(model_id)
        # OpenAI-compatible model APIs may publish a context_window. Do not
        # infer it from max output tokens or other similarly named fields.
        context_tokens = _positive_int(item.get("context_window"))
        if context_tokens is not None:
            metadata[model_id] = {"context_tokens": context_tokens}
    # Keep only the two Groq headers whose meanings are documented by Groq.
    # In particular x-ratelimit-limit-requests is RPD, not RPM.
    allowed_headers = {
        "x-ratelimit-limit-requests",
        "x-ratelimit-limit-tokens",
    }
    safe_headers = {
        name.lower(): value
        for name, value in response.headers.items()
        if name.lower() in allowed_headers and _positive_int(value) is not None
    }
    return response.status_code, sorted(ids), False, metadata, safe_headers


async def _openrouter_key_info(key: str) -> dict[str, int]:
    """Read OpenRouter's documented per-key free-model daily allowance.

    Credit budgets and the deprecated rate_limit object are intentionally
    excluded: they are not RPM/RPD/TPM values for the shared model catalogue.
    """
    try:
        async with httpx.AsyncClient(timeout=_LIST_TIMEOUT_SECONDS) as client:
            response = await client.get(
                "https://openrouter.ai/api/v1/key",
                headers={"Authorization": f"Bearer {key}"},
            )
        if response.status_code != 200:
            return {}
        payload = response.json()
    except Exception:  # noqa: BLE001 — optional metadata check must not invalidate a good key
        return {}
    data = payload.get("data", {}) if isinstance(payload, dict) else {}
    free_limits = (
        data.get("free_model_daily_requests", {})
        if isinstance(data, dict)
        else {}
    )
    if not isinstance(free_limits, dict):
        return {}
    limit = _positive_int(free_limits.get("limit"))
    return {"free_model_requests_per_day": limit} if limit is not None else {}


def _positive_int(value: object) -> int | None:
    """Parse an actual positive integer (or digit-only header) without coercion."""
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value if value > 0 else None
    if isinstance(value, str) and value.strip().isascii() and value.strip().isdecimal():
        try:
            parsed = int(value.strip())
        except ValueError:
            return None
        return parsed if parsed > 0 else None
    return None


def _build_key_metadata_verification(
    provider_id: str,
    spec: object,
    listed: list[str] | None,
    model_metadata: dict[str, dict[str, int]],
    quota_headers: dict[str, str],
    openrouter_key_info: dict[str, int],
    *,
    model_availability: dict[str, bool | None] | None = None,
) -> KeyMetadataVerification:
    """Create a redacted, per-key observation; never modify models.yaml."""
    from src.providers.config import ProviderSpec

    if not isinstance(spec, ProviderSpec):
        raise TypeError("spec must be a ProviderSpec")
    listed_set = set(listed or [])
    models = [
        VerifiedModelMetadata(
            id=model.id,
            available=(model_availability.get(model.id) if model_availability is not None else ((model.id in listed_set) if listed is not None else None)),
            context_tokens=model_metadata.get(model.id, {}).get("context_tokens"),
            output_tokens=model_metadata.get(model.id, {}).get("output_tokens"),
        )
        for model in spec.models
    ]
    observations: list[ObservedQuota] = []
    if provider_id == "groq":
        documented = (
            ("x-ratelimit-limit-requests", "rpd", "requests/day"),
            ("x-ratelimit-limit-tokens", "tpm", "tokens/minute"),
        )
        for header, field, unit in documented:
            value = _positive_int(quota_headers.get(header))
            if value is not None:
                observations.append(
                    ObservedQuota(
                        field=field,
                        value=value,
                        unit=unit,
                        scope="organization",
                        source=f"Groq response header: {header}",
                    )
                )
    if provider_id == "openrouter":
        value = _positive_int(openrouter_key_info.get("free_model_requests_per_day"))
        if value is not None:
            observations.append(
                ObservedQuota(
                    field="free_model_requests_per_day",
                    value=value,
                    unit="requests/day",
                    scope="account (free-model policy)",
                    source="OpenRouter GET /api/v1/key data.free_model_daily_requests.limit",
                )
            )

    observed_fields = {item.field for item in observations}
    context_verified = bool(models) and all(
        model.context_tokens is not None for model in models if model.available
    ) and all(model.available for model in models)
    unverified_fields: list[str] = []
    if provider_id == "gemini":
        unverified_fields.extend(["rpm", "rpd", "tpm"])
    elif provider_id == "groq":
        if "rpd" not in observed_fields:
            unverified_fields.append("rpd")
        if "tpm" not in observed_fields:
            unverified_fields.append("tpm")
        unverified_fields.append("rpm")
    elif provider_id == "openrouter":
        unverified_fields.extend(["rpm", "rpd", "tpm"])
    else:
        unverified_fields.extend(["rpm", "rpd", "tpm"])
    if not context_verified:
        unverified_fields.append("context_tokens")

    limits_issue = (
        provider_limits_issue(provider_id, spec)
        if spec.enabled
        else "Provider is disabled in models.yaml; a valid key does not enable routing."
    )
    return KeyMetadataVerification(
        checked_at=datetime.now(UTC).isoformat(),
        provider_enabled=spec.enabled,
        model_catalog_checked=True,
        models=models,
        observed_quotas=observations,
        unverified_fields=unverified_fields,
        quota_metadata_ready=spec.enabled and limits_issue is None,
        quota_metadata_issue=limits_issue,
        note=(
            "These are observations for this API key/account only. They do not "
            "change shared models.yaml values or refresh quota_last_verified. "
            "Review the provider dashboard before making a shared configuration change."
        ),
    )

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
    invalid_key_signal: bool = False,
) -> KeyTestResponse:
    """Classify using status plus a redacted provider invalid-key signal."""
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
    if list_status in (401, 403) or (list_status == 400 and invalid_key_signal):
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
