"""
Assembly — Hugging Face Provider

Implements the AIProvider interface for Hugging Face Inference API.
Uses the huggingface_hub InferenceClient for chat completions.
"""

from pydantic import SecretStr

from src.core.config import settings
from src.core.keystore import reveal
from src.core.logging_config import logger
from src.providers.base import AIProvider, ChatMessage, ProviderResponse


class HuggingFaceProvider(AIProvider):
    """Hugging Face Inference API provider (optional; disabled by default)."""

    provider_name = "huggingface"

    def __init__(
        self,
        api_key: str | SecretStr = "",
        default_model: str = "",
        models: list[str] | None = None,
    ) -> None:
        if not default_model:
            raise ValueError(
                "HuggingFaceProvider needs default_model (from models.yaml)"
            )
        key = reveal(api_key) or reveal(settings.huggingface_api_key)
        from huggingface_hub import InferenceClient

        self.client = InferenceClient(api_key=key)
        self.default_model = default_model
        self._models = list(models) if models else [default_model]

    async def generate(
        self,
        messages: list[ChatMessage],
        model: str | None = None,
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

    def get_available_models(self) -> list[str]:
        return list(self._models)
