"""
Assembly — Google Gemini Provider

Implements the AIProvider interface for Google Gemini models.
"""

from typing import List, Optional
import google.generativeai as genai

from src.providers.base import AIProvider, ChatMessage, ProviderResponse
from src.core.config import settings
from src.core.logging_config import logger


class GeminiProvider(AIProvider):
    """Google Gemini provider."""

    provider_name = "gemini"

    def __init__(self):
        if settings.gemini_api_key:
            genai.configure(api_key=settings.gemini_api_key)
        self.default_model = settings.gemini_default_model

    async def generate(
        self,
        messages: List[ChatMessage],
        model: Optional[str] = None,
        temperature: float = 0.2,
        max_tokens: int = 4096,
        **kwargs,
    ) -> ProviderResponse:
        model_name = model or self.default_model
        logger.info(f"Gemini  │ Generating with {model_name}")

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

            response = await gen_model.generate_content_async(gemini_messages)

            # Estimate token counts (Gemini SDK provides usage metadata)
            input_tokens = 0
            output_tokens = 0
            if hasattr(response, "usage_metadata") and response.usage_metadata:
                input_tokens = getattr(response.usage_metadata, "prompt_token_count", 0) or 0
                output_tokens = getattr(response.usage_metadata, "candidates_token_count", 0) or 0

            return ProviderResponse(
                content=response.text or "",
                model=model_name,
                provider=self.provider_name,
                input_tokens=input_tokens,
                output_tokens=output_tokens,
                total_tokens=input_tokens + output_tokens,
            )

        except Exception as e:
            logger.error(f"Gemini  │ Error: {e}")
            raise

    def is_available(self) -> bool:
        return settings.has_provider("gemini")

    def get_available_models(self) -> List[str]:
        return ["gemini-2.0-flash", "gemini-2.5-flash", "gemini-2.5-pro"]
