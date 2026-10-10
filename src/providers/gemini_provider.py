"""
Assembly — Google Gemini Provider

Implements the AIProvider interface for Google Gemini models.
"""

import asyncio

import google.generativeai as genai
from pydantic import SecretStr

from src.core.config import settings
from src.core.keystore import clean_key
from src.core.logging_config import logger
from src.providers.base import AIProvider, ChatMessage, ProviderResponse
from src.providers.errors import RateLimited, TruncatedResponse, classify_exception

# Bound a single generation call: the legacy SDK has no timeout of its own,
# and an unbounded await here freezes the whole execution past its budget.
GENERATION_TIMEOUT_SECONDS = 120.0

# Legacy google.generativeai 0.8.6 GenerationConfig takes only
# candidate_count/stop_sequences/max_output_tokens/temperature/top_p/top_k/
# response_mime_type/response_schema/presence_penalty/frequency_penalty —
# there is NO thinking-budget parameter, so none is set (verified against
# the installed SDK; do not add one by guess).


def _finish_to_string(finish: object) -> str:
    """Normalize SDK/REST finish reasons to the REST vocabulary.

    The legacy SDK surfaces protobuf ints (STOP=1, MAX_TOKENS=2,
    SAFETY=3, ...) while REST uses strings. Unknown shapes read as "".
    """
    if finish is None:
        return ""
    if isinstance(finish, str):
        return finish.upper() or ""
    if isinstance(finish, bool):
        return ""
    if isinstance(finish, int):
        return {
            0: "UNSPECIFIED",
            1: "STOP",
            2: "MAX_TOKENS",
            3: "SAFETY",
            4: "RECITATION",
            5: "OTHER",
        }.get(finish, str(finish))
    text = str(finish).upper()
    # "FinishReason.STOP" / "finish_reason=2" shapes: keep the tail token.
    for token in ("STOP", "MAX_TOKENS", "SAFETY", "RECITATION", "OTHER"):
        if token in text:
            return token
    return text[:32]


def _extract_text_and_finish(response: object) -> tuple[str, str]:
    """Safe candidate/parts extraction. Never touches response.text.

    response.text raises ValueError when the turn carries no parts
    (MAX_TOKENS cut, safety block, empty), which the old code
    misclassified as ProviderDown → UI "invalid". Walk the structure
    instead; missing pieces read as ("", finish).
    """
    try:
        candidates = getattr(response, "candidates", None)
        if isinstance(candidates, dict):
            candidates = [candidates]
        if not candidates:
            return "", ""
        cand = candidates[0]
        if isinstance(cand, dict):
            finish = _finish_to_string(
                cand.get("finishReason", cand.get("finish_reason", ""))
            )
            content = cand.get("content", {})
            parts = content.get("parts", []) if isinstance(content, dict) else []
        else:
            finish = _finish_to_string(getattr(cand, "finish_reason", ""))
            content = getattr(cand, "content", None)
            parts = getattr(content, "parts", []) if content is not None else []
        texts: list[str] = []
        if isinstance(parts, list):
            for part in parts:
                if isinstance(part, dict):
                    text = part.get("text", "")
                else:
                    text = getattr(part, "text", "")
                if isinstance(text, str) and text:
                    texts.append(text)
        return "".join(texts), finish
    except (AttributeError, TypeError, ValueError):
        return "", ""


class GeminiProvider(AIProvider):
    """Google Gemini provider. Raises the shared errors.ProviderError types."""

    provider_name = "gemini"

    def __init__(
        self,
        api_key: str | SecretStr = "",
        default_model: str = "",
        models: list[str] | None = None,
    ) -> None:
        if not default_model:
            raise ValueError("GeminiProvider needs default_model (from models.yaml)")
        key = clean_key(api_key) or clean_key(settings.gemini_api_key)
        if key:
            genai.configure(api_key=key)
        # SecretStr so the value never renders in logs/repr; revealed only
        # for the quota fingerprint at the call site below.
        self._api_key = SecretStr(key)
        self.default_model = default_model
        self._models = list(models) if models else [default_model]
        from src.providers.quota import fingerprint_key

        self._fingerprint = fingerprint_key(key) if key else ""

    async def generate(
        self,
        messages: list[ChatMessage],
        model: str | None = None,
        temperature: float = 0.2,
        max_tokens: int = 4096,
        **kwargs,
    ) -> ProviderResponse:
        from src.providers.quota import get_limiter

        model_name = model or self.default_model
        logger.info(f"Gemini  │ Generating with {model_name}")

        limiter = get_limiter()
        try:
            reserve = max(0, int(settings.tokens_reasoning_reserve))
        except (AttributeError, TypeError, ValueError):
            reserve = 0
        try:
            async with await limiter.acquire(
                self.provider_name,
                self._fingerprint,
                model_name,
                est_tokens=max_tokens + reserve,
            ):
                return await self._generate_inner(
                    messages, model_name, temperature, max_tokens
                )
        except RateLimited as exc:
            limiter.report_429(
                self.provider_name, self._fingerprint, model_name, exc.retry_after
            )
            raise

    async def _generate_inner(
        self,
        messages: list[ChatMessage],
        model_name: str,
        temperature: float,
        max_tokens: int,
    ) -> ProviderResponse:
        try:
            # Convert ChatMessage format to Gemini's format
            # Gemini uses 'user' and 'model' roles, and system goes into system_instruction
            system_instruction = None
            gemini_messages = []

            for msg in messages:
                if msg.role == "system":
                    system_instruction = msg.content
                else:
                    role = "model" if msg.role == "assistant" else "user"
                    gemini_messages.append({"role": role, "parts": [msg.content]})

            gen_model = genai.GenerativeModel(
                model_name=model_name,
                system_instruction=system_instruction,
                generation_config=genai.GenerationConfig(
                    temperature=temperature,
                    max_output_tokens=max_tokens,
                ),
            )

            limiter = None
            try:
                from src.providers.quota import get_limiter

                limiter = get_limiter()
            except ImportError:
                limiter = None
            try:
                reserve = max(0, int(settings.tokens_reasoning_reserve))
            except (AttributeError, TypeError, ValueError):
                reserve = 0
            if limiter is None:
                # Fail-open: no quota guard when the limiter is unavailable.
                response = await asyncio.wait_for(
                    gen_model.generate_content_async(gemini_messages),
                    timeout=GENERATION_TIMEOUT_SECONDS,
                )
            else:
                try:
                    async with await limiter.acquire(
                        "gemini",
                        self._fingerprint,
                        model_name,
                        est_tokens=max_tokens + reserve,
                    ):
                        response = await asyncio.wait_for(
                            gen_model.generate_content_async(gemini_messages),
                            timeout=GENERATION_TIMEOUT_SECONDS,
                        )
                except RateLimited as exc:
                    limiter.report_429(
                        "gemini", self._fingerprint, model_name, exc.retry_after
                    )
                    raise

            # Estimate token counts (Gemini SDK provides usage metadata)
            input_tokens = 0
            output_tokens = 0
            reasoning_tokens = 0
            if hasattr(response, "usage_metadata") and response.usage_metadata:
                input_tokens = (
                    getattr(response.usage_metadata, "prompt_token_count", 0) or 0
                )
                output_tokens = (
                    getattr(response.usage_metadata, "candidates_token_count", 0) or 0
                )
                reasoning_tokens = self._extract_reasoning_tokens(
                    response.usage_metadata
                )

            content, finish_reason = _extract_text_and_finish(response)
            if not content.strip():
                # Key worked, turn produced nothing usable: distinct type,
                # never an auth error (the key Test reports this as valid).
                raise TruncatedResponse(
                    self.provider_name,
                    f"empty generation (finish={finish_reason or 'unknown'})",
                )
            return ProviderResponse(
                content=content,
                model=model_name,
                provider=self.provider_name,
                input_tokens=input_tokens,
                output_tokens=output_tokens,
                total_tokens=input_tokens + output_tokens,
                reasoning_tokens=reasoning_tokens,
                finish_reason=finish_reason or "stop",
            )

        except Exception as e:
            structured = classify_exception(self.provider_name, e)
            logger.error(f"Gemini  │ Error: {structured}")
            raise structured from e

    def is_available(self) -> bool:
        return settings.has_provider("gemini")

    def get_available_models(self) -> list[str]:
        return list(self._models)

    @staticmethod
    def _extract_reasoning_tokens(usage_metadata: object) -> int:
        """Best-effort thinking/reasoning tokens from Gemini usage metadata.

        The surface varies by SDK and API version: the legacy
        ``google.generativeai`` SDK exposes snake_case attributes while the
        REST API (and newer SDKs) use camelCase ``thoughtsTokenCount``.
        Every known equivalent is probed; unknown shapes read as 0.
        Informational per call; the tpm lease instead reserves a measured
        average up front because actuals are known too late.
        """
        names = (
            "thoughts_token_count",
            "thoughtsTokenCount",
            "thought_token_count",
            "thoughtTokenCount",
            "reasoning_token_count",
            "reasoningTokenCount",
            "reasoning_tokens",
            "reasoningTokens",
        )
        if isinstance(usage_metadata, dict):
            for name in names:
                try:
                    value = usage_metadata.get(name, 0) or 0
                except (AttributeError, TypeError, ValueError):
                    continue
                if isinstance(value, (int, float)) and value:
                    return int(value)
            return 0
        for attr in names:
            try:
                value = getattr(usage_metadata, attr, 0) or 0
            except (AttributeError, TypeError, ValueError):
                continue
            if isinstance(value, (int, float)) and value:
                return int(value)
        return 0
