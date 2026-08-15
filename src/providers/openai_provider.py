"""
Assembly — OpenAI Provider

Implements the AIProvider interface for OpenAI models (GPT-4o, GPT-4o-mini).
"""

from typing import List, Optional
import openai

from src.providers.base import AIProvider, ChatMessage, ProviderResponse
from src.core.config import settings
from src.core.logging_config import logger


class OpenAIProvider(AIProvider):
    """OpenAI / GPT provider."""

    provider_name = "openai"

    def __init__(self):
        self.client = openai.AsyncOpenAI(api_key=settings.openai_api_key)
        self.default_model = settings.openai_default_model

    async def generate(
        self,
        messages: List[ChatMessage],
        model: Optional[str] = None,
        temperature: float = 0.2,
        max_tokens: int = 4096,
        **kwargs,
    ) -> ProviderResponse:
        model = model or self.default_model
        logger.info(f"OpenAI  │ Generating with {model}")

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
            logger.error(f"OpenAI  │ Error: {e}")
            raise

    def is_available(self) -> bool:
        return settings.has_provider("openai")

    def get_available_models(self) -> List[str]:
        return ["gpt-4o", "gpt-4o-mini", "gpt-4.1-mini", "gpt-4.1-nano"]
