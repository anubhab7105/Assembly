"""
Assembly — structured provider errors.

Every provider raises these (never raw SDK/HTTP exceptions) so the
orchestration layer can react uniformly: back off on RateLimited,
drop the key on AuthError, fail over on ProviderDown, retry-or-fallback
on BadResponse.
"""

from email.utils import parsedate_to_datetime


class ProviderError(Exception):
    """Base class for all provider failures. Carries the provider id."""

    def __init__(self, provider: str, message: str) -> None:
        super().__init__(f"{provider}: {message}")
        self.provider = provider
        self.message = message


class RateLimited(ProviderError):
    """HTTP 429. retry_after is seconds (from Retry-After) or None."""

    def __init__(
        self, provider: str, message: str, retry_after: float | None = None
    ) -> None:
        super().__init__(provider, message)
        self.retry_after = retry_after


class AuthError(ProviderError):
    """HTTP 401/403: key missing, invalid, or revoked. Never retry."""


class ProviderDown(ProviderError):
    """Timeouts, connection errors, 5xx: the provider is unreachable."""


class BadResponse(ProviderError):
    """The provider answered but the payload was unusable (400/404 model id,
    malformed JSON, empty choices). Never retry blindly."""


class TruncatedResponse(BadResponse):
    """The provider answered but returned no usable text (MAX_TOKENS,
    safety block, or empty parts).

    Distinct from AuthError on purpose: the key worked, the turn did
    not produce content. Callers that only care about key validity
    (e.g. the key Test) treat this as valid; runs treat it as a
    retry-or-fallback like any other BadResponse.
    """


class ToolCallError(BadResponse):
    """The model tried to call a native tool (e.g. web search) that the
    request did not define, so the provider refused the turn.

    Observed live on Groq gpt-oss (HTTP 400, code ``tool_use_failed``:
    "Tool choice is none, but model called a tool") when the researcher
    prompt asks for web research: the model emits ``browser.search`` and
    Groq rejects the call because no tools were supplied. Assembly never
    sends tools/tool_choice (providers/unified JSON contract), so this is
    a model-capability mismatch, not a transient outage: unlike other
    BadResponse cases it IS worth one fallback to another family via the
    circuit-breaker path, never a blind retry of the same model."""


def parse_retry_after(value: str | None) -> float | None:
    """Parse a Retry-After header (delta-seconds or HTTP-date) to seconds."""
    if not value:
        return None
    value = value.strip()
    try:
        return max(0.0, float(value))
    except ValueError:
        pass
    try:
        from datetime import datetime, timezone

        retry_at = parsedate_to_datetime(value)
        now = datetime.now(timezone.utc)
        return max(0.0, (retry_at - now).total_seconds())
    except (ValueError, TypeError, OverflowError):
        return None


def classify_http_error(
    provider: str,
    status: int,
    message: str,
    retry_after: float | None = None,
) -> ProviderError:
    """Map an HTTP status to the matching structured error type."""
    if status == 429:
        return RateLimited(provider, message, retry_after=retry_after)
    if status in (401, 403):
        return AuthError(provider, message)
    if status >= 500:
        return ProviderDown(provider, message)
    return BadResponse(provider, message)


def classify_exception(provider: str, exc: BaseException) -> ProviderError:
    """Best-effort translation of SDK/transport exceptions.

    Order matters: structured errors pass through untouched, then explicit
    status carriers (httpx, google-api-core), then timeouts, then message
    sniffing as a last resort. Unknown failures become ProviderDown so the
    orchestrator fails over instead of crashing.
    """
    if isinstance(exc, ProviderError):
        return exc
    if isinstance(exc, (TimeoutError,)):
        return ProviderDown(provider, f"timed out: {exc}")
    try:
        import httpx  # Local import: errors.py must not require httpx at module load.

        if isinstance(exc, httpx.TimeoutException):
            return ProviderDown(provider, f"timed out: {exc}")
        if isinstance(exc, httpx.HTTPStatusError):
            response = exc.response
            retry_after = None
            if response.status_code == 429:
                retry_after = parse_retry_after(response.headers.get("retry-after"))
            return classify_http_error(
                provider, response.status_code, str(exc), retry_after=retry_after
            )
        if isinstance(exc, httpx.HTTPError):
            return ProviderDown(provider, str(exc))
    except ImportError:
        pass
    status = getattr(exc, "status_code", getattr(exc, "code", None))
    if isinstance(status, int):
        return classify_http_error(provider, status, str(exc))
    text = str(exc).lower()
    if "429" in text or "rate limit" in text or "rate-limit" in text:
        return RateLimited(provider, str(exc))
    if (
        "401" in text
        or "403" in text
        or "unauthorized" in text
        or "invalid api key" in text
    ):
        return AuthError(provider, str(exc))
    if "timed out" in text or "timeout" in text or "deadline exceeded" in text:
        return ProviderDown(provider, str(exc))
    return ProviderDown(provider, str(exc))
