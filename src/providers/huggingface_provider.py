"""
Assembly — Hugging Face Provider

Implements the AIProvider interface for Hugging Face Inference API.
Uses the huggingface_hub InferenceClient for chat completions.
"""

from typing import List, Optional

from src.providers.base import AIProvider, ChatMessage, ProviderResponse
from src.core.config import settings
from src.core.logging_config import logger


class HuggingFaceProvider(AIProvider):
    """Hugging Face Inference API provider."""

    provider_name = "huggingface"

    def __init__(self):
        from huggingface_hub import InferenceClient
        self.client = InferenceClient(
            api_key=settings.huggingface_api_key,
        )
        self.default_model = settings.huggingface_default_model

    async def generate(
        self,
        messages: List[ChatMessage],
        model: Optional[str] = None,
        temperature: float = 0.2,
        max_tokens: int = 4096,
        **kwargs,
    ) -> ProviderResponse:
        import asyncio
        model = model or self.default_model
        logger.info(f"HuggingFace │ Generating with {model}")

        try:
            # huggingface_hub InferenceClient is synchronous,
            # so we run it in a thread executor to avoid blocking the event loop
            hf_messages = [{"role": m.role, "content": m.content} for m in messages]

            def _call():
                return self.client.chat_completion(
                    model=model,
                    messages=hf_messages,
                    temperature=temperature,
                    max_tokens=max_tokens,
                )

            loop = asyncio.get_event_loop()
            response = await loop.run_in_executor(None, _call)

            # Extract response data
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
            logger.error(f"HuggingFace │ Error: {e}")
            raise

    def is_available(self) -> bool:
        return settings.has_provider("huggingface")

    def get_available_models(self) -> List[str]:
        return [
            "meta-llama/Meta-Llama-3-8B-Instruct",
            "mistralai/Mistral-7B-Instruct-v0.3",
            "microsoft/Phi-3-mini-4k-instruct",
        ]
