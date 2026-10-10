"""
Assembly — generic OpenAI-compatible chat provider (async httpx).

One class drives Groq, Cerebras, OpenRouter, Mistral, and NVIDIA: all
expose POST {base_url}/chat/completions with the OpenAI body shape.
Endpoint, model id, headers, and timeout come from models.yaml via the
registry — nothing provider-specific lives here.

Retry policy: only idempotent transient failures are retried —
HTTP 429 (honoring Retry-After), 502/503/504, timeouts, and connection
errors — with exponential backoff and a bounded attempt count. 401/403
(AuthError) and 400/404/malformed payloads (BadResponse) never retry.
"""

import asyncio
from typing import Any

import httpx
from pydantic import SecretStr

from src.core.keystore import clean_key, reveal
from src.core.logging_config import logger
from src.providers.base import AIProvider, ChatMessage, ProviderResponse
from src.providers.errors import (
    AuthError,
    BadResponse,
    ProviderDown,
    RateLimited,
    ToolCallError,
    classify_http_error,
    parse_retry_after,
)

# Statuses safe to retry on a POST chat-completion call: the call has no
# server-side side effects, so a retry cannot double-apply anything.
RETRYABLE_STATUSES = frozenset({429, 502, 503, 504})
MAX_BACKOFF_SECONDS = 60.0


def _reasoning_reserve_tokens() -> int:
    """Extra headroom added to the tpm lease for unreported reasoning.

    Reasoning/thinking tokens are billed against per-minute token windows
    but are only known AFTER the call. Reserve the measured average so
    the pre-send tpm guard stays conservative. Fail-open: any trouble
    reading config yields 0 (leases behave exactly as before).
    """
    try:
        from src.core.config import settings

        return max(0, int(settings.tokens_reasoning_reserve))
    except (AttributeError, TypeError, ValueError):
        return 0


def _tool_use_failure_message(
    status: int, body: Any, fallback_message: str
) -> str | None:
    """Detect a refused native tool-call turn (Groq gpt-oss browser.search).

    Returns the provider's message when the body carries a tool-use
    failure (code ``tool_use_failed`` or the "tool choice is none"
    wording), else None. Pure: safe to unit-test with canned bodies.
    """
    if status != 400 or not isinstance(body, dict):
        return None
    error = body.get("error")
    if not isinstance(error, dict):
        return None
    code = str(error.get("code", ""))
    message = str(error.get("message", "") or fallback_message)
    if code == "tool_use_failed" or "tool choice is none" in message.casefold():
        return message[:500]
    nested = str(error.get("failed_generation", ""))
    if "tool choice is none" in (message + nested).casefold():
        return message[:500]
    return None


class OpenAICompatibleProvider(AIProvider):
    """Single httpx implementation for every OpenAI-compatible backend."""

    def __init__(
        self,
        provider_id: str,
        api_key: str | SecretStr,
        base_url: str,
        default_model: str,
        models: list[str] | None = None,
        extra_headers: dict[str, str] | None = None,
        timeout_seconds: float = 60.0,
        max_retries: int = 2,
    ) -> None:
        value = clean_key(api_key)
        if not value:
            raise AuthError(provider_id, "missing API key")
        from src.providers.quota import fingerprint_key

        self.provider_name = provider_id
        self._api_key = SecretStr(value)
        self._fingerprint = fingerprint_key(value)
        self._base_url = base_url.rstrip("/")
        self._default_model = default_model
        self._models = list(models) if models else [default_model]
        self._extra_headers = dict(extra_headers or {})
        self._timeout = httpx.Timeout(timeout_seconds)
        self._max_retries = max(0, max_retries)

    def is_available(self) -> bool:
        return bool(reveal(self._api_key))

    def get_available_models(self) -> list[str]:
        return list(self._models)

    async def generate(
        self,
        messages: list[ChatMessage],
        model: str | None = None,
        temperature: float = 0.2,
        max_tokens: int = 4096,
        **kwargs: Any,
    ) -> ProviderResponse:
        from src.providers.quota import get_limiter

        model_name = model or self._default_model
        logger.info(f"Provider │ {self.provider_name} generating with {model_name}")
        # NOTE: no tools/tool_choice are ever sent. Groq documents built-in
        # browser search as opt-in (tools=[{"type": "browser_search"}] +
        # tool_choice) with no disable flag, so omitting tools is already
        # the correct posture — yet gpt-oss still emits native browser.search
        # turns on research-flavored prompts (live: exact production
        # researcher prompt 400s 3/3 with code tool_use_failed; shorter
        # prompts usually pass). Those turns surface as ToolCallError below
        # and fail over to another family instead of retrying the same model.
        payload = {
            "model": model_name,
            "messages": [{"role": m.role, "content": m.content} for m in messages],
            "temperature": temperature,
            "max_tokens": max_tokens,
        }
        limiter = get_limiter()
        try:
            async with await limiter.acquire(
                self.provider_name,
                self._fingerprint,
                model_name,
                est_tokens=max_tokens + _reasoning_reserve_tokens(),
            ):
                data = await self._post_with_retry(payload)
        except RateLimited as exc:
            limiter.report_429(
                self.provider_name, self._fingerprint, model_name, exc.retry_after
            )
            raise
        return self._to_response(data, model_name)

    async def _post_with_retry(self, payload: dict[str, Any]) -> dict[str, Any]:
        """POST chat/completions, retrying only transient failures."""
        headers = {
            "Authorization": f"Bearer {reveal(self._api_key)}",
            **self._extra_headers,
        }
        last_error: Exception | None = None
        async with httpx.AsyncClient(timeout=self._timeout) as client:
            for attempt in range(self._max_retries + 1):
                try:
                    response = await client.post(
                        f"{self._base_url}/chat/completions",
                        json=payload,
                        headers=headers,
                    )
                    if response.status_code == 200:
                        try:
                            body: Any = response.json()
                        except ValueError as exc:
                            raise BadResponse(
                                self.provider_name, f"response body is not JSON: {exc}"
                            ) from exc
                        if not isinstance(body, dict):
                            raise BadResponse(
                                self.provider_name, "response body is not a JSON object"
                            )
                        return body
                    if (
                        response.status_code in RETRYABLE_STATUSES
                        and attempt < self._max_retries
                    ):
                        await asyncio.sleep(self._backoff_seconds(response, attempt))
                        continue
                    body: Any = None
                    try:
                        parsed: Any = response.json()
                        if isinstance(parsed, dict):
                            body = parsed
                    except ValueError:
                        body = None
                    tool_message = _tool_use_failure_message(
                        response.status_code,
                        body,
                        self._error_message(response),
                    )
                    if tool_message is not None:
                        raise ToolCallError(self.provider_name, tool_message)
                    raise classify_http_error(
                        self.provider_name,
                        response.status_code,
                        self._error_message(response),
                        retry_after=parse_retry_after(
                            response.headers.get("retry-after")
                        )
                        if response.status_code == 429
                        else None,
                    )
                except (httpx.TimeoutException, httpx.ConnectError) as exc:
                    last_error = ProviderDown(
                        self.provider_name, f"{type(exc).__name__}: {exc}"
                    )
                    if attempt < self._max_retries:
                        await asyncio.sleep(2.0**attempt)
                        continue
                    raise last_error from exc
                except httpx.HTTPError as exc:
                    raise ProviderDown(self.provider_name, str(exc)) from exc
        # Unreachable: the loop always returns or raises.
        raise last_error or ProviderDown(self.provider_name, "request failed")

    def _backoff_seconds(self, response: httpx.Response, attempt: int) -> float:
        """Retry-After (capped) for 429s, exponential backoff otherwise."""
        if response.status_code == 429:
            retry_after = parse_retry_after(response.headers.get("retry-after"))
            if retry_after is not None:
                return min(retry_after, MAX_BACKOFF_SECONDS)
        return min(2.0**attempt, MAX_BACKOFF_SECONDS)

    @staticmethod
    def _error_message(response: httpx.Response) -> str:
        """Best-effort message without echoing secrets (key is header-only)."""
        try:
            body: Any = response.json()
            if isinstance(body, dict):
                error = body.get("error")
                if isinstance(error, dict) and error.get("message"):
                    return str(error["message"])[:500]
                if isinstance(error, str):
                    return error[:500]
        except ValueError:
            pass
        return f"HTTP {response.status_code}: {response.text[:200]}"

    def _to_response(self, data: dict[str, Any], model_name: str) -> ProviderResponse:
        """Extract content + token usage; anything else is a BadResponse."""
        choices = data.get("choices")
        if not choices or not isinstance(choices, list):
            raise BadResponse(self.provider_name, "response has no choices")
        message = choices[0].get("message", {}) if isinstance(choices[0], dict) else {}
        content = message.get("content") or ""
        if not str(content).strip() and isinstance(message.get("tool_calls"), list):
            tools = [
                str(call.get("function", {}).get("name", "?"))
                for call in message["tool_calls"]
                if isinstance(call, dict)
            ]
            if tools:
                raise ToolCallError(
                    self.provider_name,
                    "Model called native tools "
                    f"({', '.join(tools)}) with no tools defined; "
                    "reply carries no usable content.",
                )
        finish = (
            choices[0].get("finish_reason", "stop")
            if isinstance(choices[0], dict)
            else "stop"
        )
        usage = data.get("usage", {}) or {}
        prompt_tokens = int(usage.get("prompt_tokens", 0) or 0)
        completion_tokens = int(usage.get("completion_tokens", 0) or 0)
        total_tokens = int(usage.get("total_tokens", 0) or 0) or (
            prompt_tokens + completion_tokens
        )
        reasoning_tokens = self._extract_reasoning_tokens(usage)
        return ProviderResponse(
            content=content,
            model=model_name,
            provider=self.provider_name,
            input_tokens=prompt_tokens,
            output_tokens=completion_tokens,
            total_tokens=total_tokens,
            reasoning_tokens=reasoning_tokens,
            finish_reason=finish or "stop",
        )

    @staticmethod
    def _extract_reasoning_tokens(usage: dict[str, Any]) -> int:
        """Best-effort reasoning/thinking tokens from OpenAI-style usage.

        Providers report this in different places: usage.reasoning_tokens,
        usage.completion_tokens_details.reasoning_tokens, or
        usage.completion_tokens_details.reasoning. Missing or malformed
        values read as 0. Reported values are informational per call; the
        tpm lease instead reserves a measured average up front (see
        _reasoning_reserve_tokens) because actuals are known too late.
        """
        try:
            direct = usage.get("reasoning_tokens")
            if isinstance(direct, (int, float)) and direct:
                return int(direct)
            details = usage.get("completion_tokens_details") or {}
            if isinstance(details, dict):
                for key in ("reasoning_tokens", "reasoning"):
                    value = details.get(key)
                    if isinstance(value, (int, float)) and value:
                        return int(value)
        except (AttributeError, TypeError, ValueError):
            pass
        return 0
