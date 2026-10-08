"""
Assembly — Groq Provider

Implements the AIProvider interface for Groq's fast inference (LLaMA models).
"""

from typing import List, Optional
from groq import AsyncGroq

from src.providers.base import AIProvider, ChatMessage, ProviderResponse
from src.core.config import settings
from src.core.logging_config import logger


class GroqProvider(AIProvider):
    """Groq fast-inference provider (LLaMA, Mixtral)."""

    provider_name = "groq"

    def __init__(self):
        self.client = AsyncGroq(api_key=settings.groq_api_key)
        self.default_model = settings.groq_default_model

    async def generate(
        self,
        messages: List[ChatMessage],
        model: Optional[str] = None,
        temperature: float = 0.2,
        max_tokens: int = 4096,
        **kwargs,
    ) -> ProviderResponse:
        model = model or self.default_model
        logger.info(f"Groq   │ Generating with {model}")

        try:
            response = await self.client.chat.completions.create(
                model=model,
                messages=[{"role": m.role, "content": m.content} for m in messages],
                temperature=temperature,
                max_tokens=max_tokens,
            )

            choice = response.choices[0]
            usage = response.usage

            return ProviderResponse(
                content=choice.message.content or "",
                model=model,
                provider=self.provider_name,
                input_tokens=usage.prompt_tokens if usage else 0,
                output_tokens=usage.completion_tokens if usage else 0,
                total_tokens=usage.total_tokens if usage else 0,
                finish_reason=choice.finish_reason or "stop",
            )

        except Exception as e:
            logger.error(f"Groq   │ Error: {e}")
            raise

    def is_available(self) -> bool:
        return settings.has_provider("groq")

    def get_available_models(self) -> List[str]:
        return ["openai/gpt-oss-20b", "openai/gpt-oss-120b", "qwen/qwen3.8-27b"]
