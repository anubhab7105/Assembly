"""
Assembly — AI Provider Base Interface

Abstract provider interface per PRD Section 19.
All providers implement this contract so models can be swapped without
rewriting the orchestration layer.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass


@dataclass
class ChatMessage:
    """A single message in a conversation."""

    role: str  # "system" | "user" | "assistant"
    content: str


@dataclass
class ProviderResponse:
    """Standardized response from any AI provider."""

    content: str
    model: str
    provider: str
    input_tokens: int = 0
    output_tokens: int = 0
    total_tokens: int = 0
    finish_reason: str = "stop"
    raw_response: dict | None = None


class AIProvider(ABC):
    """
    Abstract base class for AI providers.

    All providers must implement generate() with the same interface
    so the orchestration layer stays provider-agnostic.
    """

    provider_name: str = "base"

    @abstractmethod
    async def generate(
        self,
        messages: list[ChatMessage],
        model: str | None = None,
        temperature: float = 0.2,
        max_tokens: int = 4096,
        **kwargs,
    ) -> ProviderResponse:
        """
        Generate a completion from the given message history.

        Args:
            messages: Conversation history as ChatMessage objects.
            model: Model identifier (provider-specific). Uses default if None.
            temperature: Sampling temperature (0.0–2.0).
            max_tokens: Maximum tokens to generate.

        Returns:
            ProviderResponse with the generated content and token usage.
        """
        ...

    @abstractmethod
    def is_available(self) -> bool:
        """Check if this provider has valid credentials."""
        ...

    @abstractmethod
    def get_available_models(self) -> list[str]:
        """Return list of model identifiers this provider supports."""
        ...
