"""
Assembly — Cerebras Provider

Implements the AIProvider interface for Cerebras' ultra-fast inference.
Uses the OpenAI-compatible API at https://api.cerebras.ai/v1.
"""

from typing import List, Optional
import openai

from src.providers.base import AIProvider, ChatMessage, ProviderResponse
from src.core.config import settings
from src.core.logging_config import logger


class CerebrasProvider(AIProvider):
    """Cerebras fast-inference provider (LLaMA models via OpenAI-compatible API)."""

    provider_name = "cerebras"

    def __init__(self):
        self.client = openai.AsyncOpenAI(
            api_key=settings.cerebras_api_key,
            base_url="https://api.cerebras.ai/v1",
        )
        self.default_model = settings.cerebras_default_model

    async def generate(
        self,
        messages: List[ChatMessage],
        model: Optional[str] = None,
        temperature: float = 0.2,
        max_tokens: int = 4096,
        **kwargs,
    ) -> ProviderResponse:
        model = model or self.default_model
        logger.info(f"Cerebras │ Generating with {model}")

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
            logger.error(f"Cerebras │ Error: {e}")
            raise

    def is_available(self) -> bool:
        return settings.has_provider("cerebras")

    def get_available_models(self) -> List[str]:
        return ["gpt-oss-120b", "qwen-3.8-27b"]
