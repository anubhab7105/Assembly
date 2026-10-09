"""Assembly model verifier — live catalog + tiny-probe check, keys never printed.

Usage:
    python scripts/verify_models.py [--provider groq] [--include-disabled]
                                    [--timeout 20] [--max-tokens 5]
                                    [--save [--save PATH]]

For each ENABLED provider in models.yaml the script:
  (1) calls its models-list endpoint and reports any models.yaml id that
      the provider does not list (retired / renamed / typo);
  (2) makes ONE tiny chat request per catalog model (max_tokens=5) and
      prints the HTTP status plus any rate-limit response headers
      (x-ratelimit-*, ratelimit-*, retry-after) so real limits can be
      read off the response instead of invented;
  (3) reports any model that errors (plan-not-allowed, quota/payment,
      model-not-found, auth, rate-limited).

--save writes a markdown report to .local/verify_report.md (git-ignored):
status + classification + x-ratelimit-limit-* headers ONLY — no keys,
no remaining/reset values, no retry-after. Console output is unchanged.

Keys are loaded from .env / .env.dev (git-ignored) and revealed only at
the httpx call site. Output holds provider/model NAMES, counts,
statuses, header values, and truncated error snippets — NEVER key
material. Error snippets pass through the key-masking filter first.
"""

import argparse
import asyncio
import os
import sys
from pathlib import Path
from typing import Any

# Load local keys BEFORE importing src.* (settings reads env at import).
from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parent.parent
load_dotenv(PROJECT_ROOT / ".env", override=False)
load_dotenv(PROJECT_ROOT / ".env.dev", override=True)
sys.path.insert(0, str(PROJECT_ROOT))

import httpx
from pydantic import BaseModel, ConfigDict, Field

from src.core.logging_config import mask_text
from src.providers.config import ModelsConfig, ProviderSpec, load_models_config

GEMINI_LIST_URL = "https://generativelanguage.googleapis.com/v1beta/models"
HF_MODEL_URL = "https://huggingface.co/api/models/{model}"
HF_INFER_URL = "https://api-inference.huggingface.co/models/{model}"

DEFAULT_REPORT_PATH = PROJECT_ROOT / ".local" / "verify_report.md"

_PLACEHOLDER_PREFIXES = (
    "sk-your",
    "your-",
    "gsk_your",
    "hf_your",
    "csk_your",
    "xpl_your",
)

TINY_PROMPT = "Reply with exactly one word: ok"


class TinyProbe(BaseModel):
    """One tiny chat request and what the server said back."""

    model_config = ConfigDict(extra="forbid")

    provider: str
    model: str
    http_status: int | None = None
    ok: bool = False
    ratelimit_headers: dict[str, str] = Field(default_factory=dict)
    error_kind: str | None = None
    error_snippet: str = ""


class ProviderVerdict(BaseModel):
    """Everything observed for one provider (names and counts only)."""

    model_config = ConfigDict(extra="forbid")

    provider: str
    base: str = ""
    enabled: bool = True
    key_present: bool = False
    catalog_ids: list[str] = Field(default_factory=list)
    listed_ids: list[str] = Field(default_factory=list)
    missing_ids: list[str] = Field(default_factory=list)
    probes: list[TinyProbe] = Field(default_factory=list)
    list_status: int | None = None
    list_error: str = ""
    skipped_reason: str = ""


def _is_real_key(key: str) -> bool:
    """True when a key value looks configured (not empty/placeholder)."""
    return bool(key) and not any(key.startswith(p) for p in _PLACEHOLDER_PREFIXES)


def _resolve_key(provider_id: str) -> str:
    """Reveal the local key for a provider. Callers must never print it."""
    from src.core.config import settings
    from src.core.keystore import reveal

    attr = f"{provider_id}_api_key"
    if hasattr(settings, attr):
        return reveal(getattr(settings, attr))
    return os.environ.get(f"{provider_id.upper()}_API_KEY", "")


def _ratelimit_headers(headers: httpx.Headers) -> dict[str, str]:
    """Keep only rate-limit signals; drop everything else (incl. auth)."""
    kept: dict[str, str] = {}
    for name, value in headers.items():
        lowered = name.lower()
        if "ratelimit" in lowered or lowered == "retry-after":
            kept[name] = value
    return kept


def _limit_headers(headers: dict[str, str]) -> dict[str, str]:
    """Subset safe for the saved report: limit headers only.

    Keeps x-ratelimit-limit-* (any casing); drops remaining/reset,
    retry-after, and everything else — usage counters must never land
    in a file the user pastes back.
    """
    kept: dict[str, str] = {}
    for name, value in headers.items():
        lowered = name.lower()
        if "remain" in lowered or "reset" in lowered:
            continue
        if "ratelimit" in lowered and "limit" in lowered:
            kept[name] = value
    return kept


def _snippet(text: str, limit: int = 300) -> str:
    """Masked, single-line, truncated error text safe for terminal output."""
    masked = mask_text(text or "")
    single = " ".join(masked.split())
    return single[:limit]


def _classify_probe_error(status: int | None, body: str) -> str | None:
    """Short machine-readable cause for a failed probe (None when ok)."""
    if status == 200:
        return None
    if status is None:
        return "transport-error"
    lowered = (body or "").lower()
    if status == 429 or ("rate" in lowered and "limit" in lowered):
        return "rate-limited"
    if status in (401, 403) and any(
        s in lowered for s in ("invalid api key", "unauthorized", "incorrect api key")
    ):
        return "auth-error"
    if status == 404 or any(
        s in lowered
        for s in ("does not exist", "unknown model", "not found", "no such model")
    ):
        return "model-not-found"
    if "plan" in lowered and any(
        s in lowered
        for s in (
            "not allowed",
            "not permitted",
            "not supported",
            "does not allow",
            "do not allow",
            "no access",
            "not entitled",
            "not included",
            "upgrade",
            "permission",
        )
    ):
        return "plan-not-allowed"
    if status == 402 or any(
        s in lowered for s in ("payment", "insufficient", "credit", "quota", "billing")
    ):
        return "quota/payment-required"
    if "limit" in lowered and "0" in lowered:
        return "limit-zero"
    return f"http-{status}"


def _gemini_headers(key: str) -> dict[str, str]:
    """Gemini auth via header (never in the URL query string)."""
    return {"x-goog-api-key": key, "Content-Type": "application/json"}


async def _list_openai_models(
    base_url: str,
    key: str,
    extra_headers: dict[str, str],
    timeout: float,
) -> tuple[int | None, list[str], dict[str, str], str]:
    """GET {base}/models once. Returns (status, ids, ratelimit, error)."""
    url = base_url.rstrip("/") + "/models"
    headers = {"Authorization": f"Bearer {key}", **extra_headers}
    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            response = await client.get(url, headers=headers)
    except (httpx.TimeoutException, httpx.ConnectError) as exc:
        return None, [], {}, _snippet(f"{type(exc).__name__}: {exc}")
    except httpx.HTTPError as exc:
        return None, [], {}, _snippet(f"{type(exc).__name__}: {exc}")
    ratelimit = _ratelimit_headers(response.headers)
    if response.status_code != 200:
        return response.status_code, [], ratelimit, _snippet(response.text)
    try:
        data: Any = response.json()
    except ValueError as exc:
        return response.status_code, [], ratelimit, _snippet(f"not JSON: {exc}")
    ids = sorted(
        str(item.get("id", ""))
        for item in (data.get("data", []) if isinstance(data, dict) else [])
        if isinstance(item, dict) and item.get("id")
    )
    return response.status_code, ids, ratelimit, ""


async def _probe_openai_model(
    provider: str,
    model: str,
    base_url: str,
    key: str,
    extra_headers: dict[str, str],
    timeout: float,
    max_tokens: int,
) -> TinyProbe:
    """One tiny POST {base}/chat/completions. No retries by design."""
    url = base_url.rstrip("/") + "/chat/completions"
    headers = {"Authorization": f"Bearer {key}", **extra_headers}
    payload = {
        "model": model,
        "messages": [{"role": "user", "content": TINY_PROMPT}],
        "temperature": 0,
        "max_tokens": max_tokens,
    }
    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            response = await client.post(url, json=payload, headers=headers)
    except (httpx.TimeoutException, httpx.ConnectError) as exc:
        snippet = _snippet(f"{type(exc).__name__}: {exc}")
        return TinyProbe(
            provider=provider,
            model=model,
            http_status=None,
            ok=False,
            error_kind="transport-error",
            error_snippet=snippet,
        )
    except httpx.HTTPError as exc:
        snippet = _snippet(f"{type(exc).__name__}: {exc}")
        return TinyProbe(
            provider=provider,
            model=model,
            http_status=None,
            ok=False,
            error_kind="transport-error",
            error_snippet=snippet,
        )
    ratelimit = _ratelimit_headers(response.headers)
    if response.status_code == 200:
        return TinyProbe(
            provider=provider,
            model=model,
            http_status=200,
            ok=True,
            ratelimit_headers=ratelimit,
        )
    snippet = _snippet(response.text)
    return TinyProbe(
        provider=provider,
        model=model,
        http_status=response.status_code,
        ok=False,
        ratelimit_headers=ratelimit,
        error_kind=_classify_probe_error(response.status_code, snippet),
        error_snippet=snippet,
    )


async def _list_gemini_models(
    key: str, timeout: float
) -> tuple[int | None, list[str], dict[str, str], str]:
    """GET the Gemini model catalog (header auth so the key stays out of URLs)."""
    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            response = await client.get(GEMINI_LIST_URL, headers=_gemini_headers(key))
    except (httpx.TimeoutException, httpx.ConnectError) as exc:
        return None, [], {}, _snippet(f"{type(exc).__name__}: {exc}")
    except httpx.HTTPError as exc:
        return None, [], {}, _snippet(f"{type(exc).__name__}: {exc}")
    ratelimit = _ratelimit_headers(response.headers)
    if response.status_code != 200:
        return response.status_code, [], ratelimit, _snippet(response.text)
    try:
        data: Any = response.json()
    except ValueError as exc:
        return response.status_code, [], ratelimit, _snippet(f"not JSON: {exc}")
    models = data.get("models", []) if isinstance(data, dict) else []
    ids = sorted(
        str(item.get("name", "")).replace("models/", "")
        for item in models
        if isinstance(item, dict) and item.get("name")
    )
    return response.status_code, ids, ratelimit, ""


async def _probe_gemini_model(
    model: str, key: str, timeout: float, max_tokens: int
) -> TinyProbe:
    """One tiny generateContent call for a Gemini model id."""
    url = f"{GEMINI_LIST_URL}/{model}:generateContent"
    payload = {
        "contents": [{"parts": [{"text": TINY_PROMPT}]}],
        "generationConfig": {"maxOutputTokens": max_tokens, "temperature": 0},
    }
    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            response = await client.post(
                url, json=payload, headers=_gemini_headers(key)
            )
    except (httpx.TimeoutException, httpx.ConnectError) as exc:
        return TinyProbe(
            provider="gemini",
            model=model,
            ok=False,
            error_kind="transport-error",
            error_snippet=_snippet(f"{type(exc).__name__}: {exc}"),
        )
    except httpx.HTTPError as exc:
        return TinyProbe(
            provider="gemini",
            model=model,
            ok=False,
            error_kind="transport-error",
            error_snippet=_snippet(f"{type(exc).__name__}: {exc}"),
        )
    ratelimit = _ratelimit_headers(response.headers)
    if response.status_code == 200:
        return TinyProbe(
            provider="gemini",
            model=model,
            http_status=200,
            ok=True,
            ratelimit_headers=ratelimit,
        )
    snippet = _snippet(response.text)
    return TinyProbe(
        provider="gemini",
        model=model,
        http_status=response.status_code,
        ok=False,
        ratelimit_headers=ratelimit,
        error_kind=_classify_probe_error(response.status_code, snippet),
        error_snippet=snippet,
    )


async def _check_hf_model_exists(
    client: httpx.AsyncClient, model: str, key: str
) -> bool:
    """HEAD-equivalent existence check against the public HF model API."""
    headers = {"Authorization": f"Bearer {key}"} if _is_real_key(key) else {}
    try:
        response = await client.get(HF_MODEL_URL.format(model=model), headers=headers)
    except httpx.HTTPError:
        return False
    return response.status_code == 200


async def _probe_hf_model(client: httpx.AsyncClient, model: str, key: str) -> TinyProbe:
    """One tiny HF inference call; headers + status are the signal."""
    headers = {"Authorization": f"Bearer {key}"} if _is_real_key(key) else {}
    try:
        response = await client.post(
            HF_INFER_URL.format(model=model),
            json={"inputs": TINY_PROMPT},
            headers=headers,
        )
    except (httpx.TimeoutException, httpx.ConnectError) as exc:
        return TinyProbe(
            provider="huggingface",
            model=model,
            ok=False,
            error_kind="transport-error",
            error_snippet=_snippet(f"{type(exc).__name__}: {exc}"),
        )
    except httpx.HTTPError as exc:
        return TinyProbe(
            provider="huggingface",
            model=model,
            ok=False,
            error_kind="transport-error",
            error_snippet=_snippet(f"{type(exc).__name__}: {exc}"),
        )
    ratelimit = _ratelimit_headers(response.headers)
    if response.status_code == 200:
        return TinyProbe(
            provider="huggingface",
            model=model,
            http_status=200,
            ok=True,
            ratelimit_headers=ratelimit,
        )
    snippet = _snippet(response.text)
    return TinyProbe(
        provider="huggingface",
        model=model,
        http_status=response.status_code,
        ok=False,
        ratelimit_headers=ratelimit,
        error_kind=_classify_probe_error(response.status_code, snippet),
        error_snippet=snippet,
    )


async def verify_provider(
    provider_id: str,
    spec: ProviderSpec,
    timeout: float,
    max_tokens: int,
) -> ProviderVerdict:
    """List + tiny-probe every catalog model for one provider."""
    catalog_ids = [model.id for model in spec.models]
    verdict = ProviderVerdict(
        provider=provider_id,
        base=spec.base,
        enabled=spec.enabled,
        catalog_ids=catalog_ids,
    )
    key = _resolve_key(provider_id)
    verdict.key_present = _is_real_key(key)
    if not verdict.key_present:
        verdict.skipped_reason = f"no key — set {provider_id.upper()}_API_KEY locally"
        return verdict
    if not catalog_ids:
        verdict.skipped_reason = "no models in models.yaml — add ids first"
        return verdict

    if spec.base == "openai-compatible":
        if not spec.url:
            verdict.skipped_reason = "missing 'url' for openai-compatible base"
            return verdict
        status, listed, _ratelimit, error = await _list_openai_models(
            spec.url, key, dict(spec.headers), timeout
        )
        verdict.list_status = status
        verdict.list_error = error
        verdict.listed_ids = listed
        listed_set = set(listed)
        verdict.missing_ids = [mid for mid in catalog_ids if mid not in listed_set]
        for model_id in catalog_ids:
            probe = await _probe_openai_model(
                provider_id,
                model_id,
                spec.url,
                key,
                dict(spec.headers),
                timeout,
                max_tokens,
            )
            verdict.probes.append(probe)
            await asyncio.sleep(0.5)
        return verdict

    if spec.base == "google-genai":
        status, listed, _ratelimit, error = await _list_gemini_models(key, timeout)
        verdict.list_status = status
        verdict.list_error = error
        verdict.listed_ids = listed
        listed_set = set(listed)
        verdict.missing_ids = [mid for mid in catalog_ids if mid not in listed_set]
        for model_id in catalog_ids:
            verdict.probes.append(
                await _probe_gemini_model(model_id, key, timeout, max_tokens)
            )
            await asyncio.sleep(0.5)
        return verdict

    if spec.base == "huggingface":
        async with httpx.AsyncClient(timeout=timeout) as client:
            listed: list[str] = []
            for model_id in catalog_ids:
                if await _check_hf_model_exists(client, model_id, key):
                    listed.append(model_id)
            verdict.list_status = 200 if listed else None
            verdict.listed_ids = sorted(listed)
            verdict.missing_ids = [m for m in catalog_ids if m not in set(listed)]
            for model_id in catalog_ids:
                verdict.probes.append(await _probe_hf_model(client, model_id, key))
                await asyncio.sleep(0.5)
        return verdict

    verdict.skipped_reason = f"unknown base {spec.base!r} — see models.yaml"
    return verdict


def print_verdict(verdict: ProviderVerdict) -> None:
    """Human-readable section for one provider (names/statuses only)."""
    print(f"\n== {verdict.provider} (base={verdict.base or '?'}) ==")
    if verdict.skipped_reason:
        print(f"  skipped: {verdict.skipped_reason}")
        if verdict.catalog_ids:
            print(f"  catalog ({len(verdict.catalog_ids)}):")
            for mid in verdict.catalog_ids:
                print(f"    - {mid}")
        return
    print("  key: present (value never shown)")
    print(f"  catalog ({len(verdict.catalog_ids)}):")
    for mid in verdict.catalog_ids:
        print(f"    - {mid}")
    if verdict.list_status is None:
        print(f"  list endpoint: FAILED — {verdict.list_error or 'transport error'}")
    else:
        print(
            f"  list endpoint: HTTP {verdict.list_status} "
            f"— provider lists {len(verdict.listed_ids)} model(s)"
        )
        if verdict.list_error:
            print(f"    error: {verdict.list_error}")
    if verdict.missing_ids:
        print(
            f"  MISSING from provider catalog "
            f"({len(verdict.missing_ids)} in models.yaml, not listed):"
        )
        for mid in verdict.missing_ids:
            print(f"    ! {mid}")
    else:
        print("  all catalog ids found in provider listing (or HF model API)")
    print("  tiny probes (1 request per model, max_tokens small):")
    for probe in verdict.probes:
        rl = (
            ", ".join(f"{k}={v}" for k, v in probe.ratelimit_headers.items())
            or "(no x-ratelimit-* headers)"
        )
        if probe.ok:
            print(f"    [ok] {probe.model} -> HTTP 200 | ratelimit: {rl}")
        else:
            status = probe.http_status if probe.http_status is not None else "ERR"
            print(
                f"    [FAIL] {probe.model} -> HTTP {status} "
                f"kind={probe.error_kind} | ratelimit: {rl}"
            )
            if probe.error_snippet:
                print(f"           msg: {probe.error_snippet}")


def print_summary(verdicts: list[ProviderVerdict]) -> int:
    """Final roll-up. Returns the process exit code (0/1/2)."""
    print("\n===== SUMMARY =====")
    checked = [v for v in verdicts if not v.skipped_reason]
    if not checked:
        print("nothing checked — no enabled provider had a usable local key.")
        return 2
    broken: list[str] = []
    for verdict in verdicts:
        if verdict.skipped_reason:
            print(f"  {verdict.provider}: skipped ({verdict.skipped_reason})")
            continue
        bad = [p for p in verdict.probes if not p.ok]
        tag = "OK" if not verdict.missing_ids and not bad else "NEEDS ATTENTION"
        print(
            f"  {verdict.provider}: {tag} "
            f"(catalog={len(verdict.catalog_ids)} "
            f"missing={len(verdict.missing_ids)} failed_probes={len(bad)})"
        )
        broken.extend(f"{verdict.provider}/{p.model} ({p.error_kind})" for p in bad)
        broken.extend(
            f"{verdict.provider}/{m} (not-listed)" for m in verdict.missing_ids
        )
    if broken:
        print("\nModels needing models.yaml edits or dashboard checks:")
        for item in broken:
            print(f"  - {item}")
        print("\nCopy the observed x-ratelimit-*/retry-after values above into")
        print("models.yaml (per-model limits) with a source + date comment.")
        return 1
    print("all catalog ids listed and every tiny probe returned HTTP 200.")
    return 0


async def verify_all(
    config: ModelsConfig,
    only: str | None,
    include_disabled: bool,
    timeout: float,
    max_tokens: int,
) -> list[ProviderVerdict]:
    """Verify each selected provider sequentially (gentle on free tiers)."""
    verdicts: list[ProviderVerdict] = []
    for provider_id, spec in config.providers.items():
        if only and provider_id != only:
            continue
        if not spec.enabled and not include_disabled:
            verdict = ProviderVerdict(
                provider=provider_id,
                base=spec.base,
                enabled=False,
                catalog_ids=[m.id for m in spec.models],
                skipped_reason="disabled in models.yaml (use --include-disabled)",
            )
            verdicts.append(verdict)
            continue
        verdicts.append(await verify_provider(provider_id, spec, timeout, max_tokens))
    return verdicts


def render_report(verdicts: list[ProviderVerdict]) -> str:
    """Markdown report: status + classification + limit headers only.

    Deliberately excludes remaining/reset/retry-after values, list-error
    bodies, and anything key-like — the file is meant to be pasted back
    into chat. All snippets are masked and truncated.
    """
    from datetime import datetime, timezone

    lines: list[str] = ["# Assembly verify report", ""]
    lines.append(f"Checked (UTC): {datetime.now(timezone.utc).isoformat()}")
    lines.append("")
    for verdict in verdicts:
        lines.append(f"## {verdict.provider} (base={verdict.base or '?'})")
        if verdict.skipped_reason:
            lines.append(f"- skipped: {verdict.skipped_reason}")
            lines.append("")
            continue
        lines.append(f"- list endpoint: HTTP {verdict.list_status}")
        if verdict.missing_ids:
            lines.append(
                f"- not listed ({len(verdict.missing_ids)}): "
                + ", ".join(f"`{m}`" for m in verdict.missing_ids)
            )
        else:
            lines.append("- not listed: none")
        lines.append("")
        lines.append("| model | status | classification | limit headers |")
        lines.append("| --- | --- | --- | --- |")
        for probe in verdict.probes:
            limits = _limit_headers(probe.ratelimit_headers)
            limit_text = (
                ", ".join(f"{k}={v}" for k, v in limits.items()) or "(no limit headers)"
            )
            status = str(probe.http_status) if probe.http_status is not None else "ERR"
            kind = probe.error_kind or ("ok" if probe.ok else "failed")
            lines.append(f"| `{probe.model}` | {status} | {kind} | {limit_text} |")
        lines.append("")
    return "\n".join(lines)


def save_report(verdicts: list[ProviderVerdict], path: Path) -> Path:
    """Write the markdown report, creating parent dirs. Returns the path."""
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(render_report(verdicts), encoding="utf-8")
    return target


def main(argv: list[str] | None = None) -> int:
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except (AttributeError, OSError):
        pass
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--provider", default=None, help="only check one provider id")
    parser.add_argument(
        "--include-disabled",
        action="store_true",
        help="also check providers with enabled: false",
    )
    parser.add_argument("--timeout", type=float, default=20.0)
    parser.add_argument(
        "--max-tokens",
        type=int,
        default=5,
        help="completion budget for each tiny probe (keep small)",
    )
    parser.add_argument(
        "--save",
        nargs="?",
        const=str(DEFAULT_REPORT_PATH),
        default=None,
        metavar="PATH",
        help="write a limit-headers-only markdown report "
        "(default: .local/verify_report.md)",
    )
    args = parser.parse_args(argv)

    try:
        config = load_models_config()
    except (FileNotFoundError, ValueError, TypeError) as exc:
        print(f"ABORT: cannot load models.yaml: {exc}")
        return 2
    if args.provider and args.provider not in config.providers:
        print(
            f"ABORT: unknown provider {args.provider!r}; "
            f"available: {sorted(config.providers)}"
        )
        return 2

    verdicts = asyncio.run(
        verify_all(
            config, args.provider, args.include_disabled, args.timeout, args.max_tokens
        )
    )
    for verdict in verdicts:
        print_verdict(verdict)
    code = print_summary(verdicts)
    if args.save:
        saved = save_report(verdicts, Path(args.save))
        print(f"\nSaved limit-headers report -> {saved}")
    return code


if __name__ == "__main__":
    raise SystemExit(main())
