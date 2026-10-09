"""
Assembly — Google Gemini Provider

Implements the AIProvider interface for Google Gemini models.
"""

import asyncio

import google.generativeai as genai
from pydantic import SecretStr

from src.core.config import settings
from src.core.keystore import reveal
from src.core.logging_config import logger
from src.providers.base import AIProvider, ChatMessage, ProviderResponse
from src.providers.errors import classify_exception

# Bound a single generation call: the legacy SDK has no timeout of its own,
# and an unbounded await here freezes the whole execution past its budget.
GENERATION_TIMEOUT_SECONDS = 120.0


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
        key = reveal(api_key) or reveal(settings.gemini_api_key)
        if key:
            genai.configure(api_key=key)
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
        from src.providers.errors import RateLimited
        from src.providers.quota import get_limiter

        model_name = model or self.default_model
        logger.info(f"Gemini  │ Generating with {model_name}")

        limiter = get_limiter()
        try:
            async with await limiter.acquire(
                self.provider_name,
                self._fingerprint,
                model_name,
                est_tokens=max_tokens,
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

            response = await asyncio.wait_for(
                gen_model.generate_content_async(gemini_messages),
                timeout=GENERATION_TIMEOUT_SECONDS,
            )

            # Estimate token counts (Gemini SDK provides usage metadata)
            input_tokens = 0
            output_tokens = 0
            if hasattr(response, "usage_metadata") and response.usage_metadata:
                input_tokens = (
                    getattr(response.usage_metadata, "prompt_token_count", 0) or 0
                )
                output_tokens = (
                    getattr(response.usage_metadata, "candidates_token_count", 0) or 0
                )

            return ProviderResponse(
                content=response.text or "",
                model=model_name,
                provider=self.provider_name,
                input_tokens=input_tokens,
                output_tokens=output_tokens,
                total_tokens=input_tokens + output_tokens,
            )

        except Exception as e:
            structured = classify_exception(self.provider_name, e)
            logger.error(f"Gemini  │ Error: {structured}")
            raise structured from e

    def is_available(self) -> bool:
        return settings.has_provider("gemini")

    def get_available_models(self) -> list[str]:
        return list(self._models)
