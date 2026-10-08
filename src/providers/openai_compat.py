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

from src.core.keystore import reveal
from src.core.logging_config import logger
from src.providers.base import AIProvider, ChatMessage, ProviderResponse
from src.providers.errors import (
    AuthError,
    BadResponse,
    ProviderDown,
    classify_http_error,
    parse_retry_after,
)

# Statuses safe to retry on a POST chat-completion call: the call has no
# server-side side effects, so a retry cannot double-apply anything.
RETRYABLE_STATUSES = frozenset({429, 502, 503, 504})
MAX_BACKOFF_SECONDS = 60.0


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
        value = reveal(api_key)
        if not value:
            raise AuthError(provider_id, "missing API key")
        self.provider_name = provider_id
        self._api_key = SecretStr(value)
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
        model_name = model or self._default_model
        logger.info(f"Provider │ {self.provider_name} generating with {model_name}")
        payload = {
            "model": model_name,
            "messages": [{"role": m.role, "content": m.content} for m in messages],
            "temperature": temperature,
            "max_tokens": max_tokens,
        }
        data = await self._post_with_retry(payload)
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
        return ProviderResponse(
            content=content,
            model=model_name,
            provider=self.provider_name,
            input_tokens=prompt_tokens,
            output_tokens=completion_tokens,
            total_tokens=total_tokens,
            finish_reason=finish or "stop",
        )
