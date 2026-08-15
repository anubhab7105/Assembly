"""
Assembly — Model Router

Selects the best provider + model for each agent role based on
task type, complexity, cost, latency, and time budget (PRD Section 22).
"""

from typing import Optional, Tuple
from dataclasses import dataclass

from src.providers.base import AIProvider
from src.providers.openai_provider import OpenAIProvider
from src.providers.gemini_provider import GeminiProvider
from src.providers.groq_provider import GroqProvider
from src.core.logging_config import logger


@dataclass
class ModelAssignment:
    """Result of model routing: provider instance + specific model."""
    provider: AIProvider
    model: str
    provider_name: str


class ModelRouter:
    """
    Intelligent model selection engine.
    
    Routes agent roles to the best available provider/model combination
    based on task requirements and constraints.
    """

    def __init__(self):
        self._providers: dict[str, AIProvider] = {}
        self._init_providers()

    def _init_providers(self):
        """Initialize all available providers."""
        providers = [
            ("openai", OpenAIProvider),
            ("gemini", GeminiProvider),
            ("groq", GroqProvider),
        ]
        for name, cls in providers:
            try:
                provider = cls()
                if provider.is_available():
                    self._providers[name] = provider
                    logger.info(f"Router  │ ✓ {name} provider available")
                else:
                    logger.warning(f"Router  │ ✗ {name} provider — no API key")
            except Exception as e:
                logger.warning(f"Router  │ ✗ {name} provider — init error: {e}")

    def get_available_providers(self) -> list[str]:
        """Return names of providers with valid credentials."""
        return list(self._providers.keys())

    def route(
        self,
        agent_type: str,
        problem_type: str = "general",
        complexity: str = "medium",
        time_budget_minutes: int = 5,
        prefer_provider: Optional[str] = None,
    ) -> ModelAssignment:
        """
        Route an agent to the best available model.
        
        Strategy:
        - Solver/Analyst → strongest reasoning model (GPT-4o, Gemini 2.5 Pro)
        - Researcher → model with good comprehension (Gemini Flash, GPT-4o-mini)
        - Critic → strong reasoning (GPT-4o, Gemini 2.5 Pro)
        - Synthesizer → good writing model (GPT-4o-mini, Gemini Flash)
        - Short time budgets → prefer fast/low-latency (Groq, GPT-4o-mini)
        """

        if not self._providers:
            raise RuntimeError("No AI providers configured. Please add API keys to .env")

        # If a specific provider is requested and available, use it
        if prefer_provider and prefer_provider in self._providers:
            provider = self._providers[prefer_provider]
            return ModelAssignment(
                provider=provider,
                model=provider.get_available_models()[0],
                provider_name=prefer_provider,
            )

        # ── Routing Logic ────────────────────────────────────────────
        # Build a priority list of (provider_name, model) tuples
        routing_table = self._get_routing_table(agent_type, problem_type, complexity, time_budget_minutes)

        # Find the first available provider/model combination
        for provider_name, model in routing_table:
            if provider_name in self._providers:
                return ModelAssignment(
                    provider=self._providers[provider_name],
                    model=model,
                    provider_name=provider_name,
                )

        # Fallback: use whatever is available
        first_name = next(iter(self._providers))
        first_provider = self._providers[first_name]
        return ModelAssignment(
            provider=first_provider,
            model=first_provider.get_available_models()[0],
            provider_name=first_name,
        )

    def _get_routing_table(
        self,
        agent_type: str,
        problem_type: str,
        complexity: str,
        time_budget_minutes: int,
    ) -> list[Tuple[str, str]]:
        """
        Build priority-ordered routing table based on the task.
        Returns list of (provider_name, model) tuples.
        """

        # For tight time budgets, prefer fast models
        if time_budget_minutes <= 3:
            return [
                ("groq", "llama-3.3-70b-versatile"),
                ("openai", "gpt-4o-mini"),
                ("gemini", "gemini-2.0-flash"),
            ]

        if agent_type == "solver":
            if problem_type == "math":
                return [
                    ("openai", "gpt-4o"),
                    ("gemini", "gemini-2.5-flash"),
                    ("groq", "llama-3.3-70b-versatile"),
                ]
            elif problem_type == "coding":
                return [
                    ("openai", "gpt-4o"),
                    ("gemini", "gemini-2.5-flash"),
                    ("groq", "llama-3.3-70b-versatile"),
                ]
            else:
                return [
                    ("openai", "gpt-4o-mini"),
                    ("gemini", "gemini-2.0-flash"),
                    ("groq", "llama-3.3-70b-versatile"),
                ]

        elif agent_type == "researcher":
            return [
                ("gemini", "gemini-2.0-flash"),
                ("openai", "gpt-4o-mini"),
                ("groq", "llama-3.1-8b-instant"),
            ]

        elif agent_type == "critic":
            if complexity == "high":
                return [
                    ("openai", "gpt-4o"),
                    ("gemini", "gemini-2.5-flash"),
                    ("groq", "llama-3.3-70b-versatile"),
                ]
            return [
                ("openai", "gpt-4o-mini"),
                ("gemini", "gemini-2.0-flash"),
                ("groq", "llama-3.3-70b-versatile"),
            ]

        elif agent_type == "synthesizer":
            return [
                ("openai", "gpt-4o-mini"),
                ("gemini", "gemini-2.0-flash"),
                ("groq", "llama-3.3-70b-versatile"),
            ]

        # Default fallback
        return [
            ("openai", "gpt-4o-mini"),
            ("gemini", "gemini-2.0-flash"),
            ("groq", "llama-3.1-8b-instant"),
        ]

    def route_for_planning(self) -> ModelAssignment:
        """Route specifically for the Planner (problem classification)."""
        routing = [
            ("openai", "gpt-4o-mini"),
            ("gemini", "gemini-2.0-flash"),
            ("groq", "llama-3.3-70b-versatile"),
        ]
        for provider_name, model in routing:
            if provider_name in self._providers:
                return ModelAssignment(
                    provider=self._providers[provider_name],
                    model=model,
                    provider_name=provider_name,
                )
        first_name = next(iter(self._providers))
        first_provider = self._providers[first_name]
        return ModelAssignment(
            provider=first_provider,
            model=first_provider.get_available_models()[0],
            provider_name=first_name,
        )
