"""
Assembly — Model Router

Selects the best provider + model for each agent role based on
task type, complexity, cost, latency, and time budget (PRD Section 22).

Supports 6 providers: Gemini, Groq, Cerebras, OpenRouter, Hugging Face, Experiential.
Enforces a minimum of 3 live providers before accepting any work.
"""

from typing import Optional, Tuple
from dataclasses import dataclass

from src.providers.base import AIProvider
from src.providers.gemini_provider import GeminiProvider
from src.providers.groq_provider import GroqProvider
from src.providers.cerebras_provider import CerebrasProvider
from src.providers.openrouter_provider import OpenRouterProvider
from src.providers.huggingface_provider import HuggingFaceProvider
from src.core.logging_config import logger

MIN_REQUIRED_PROVIDERS = 3


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
    
    Requires at least 3 live providers to operate.
    """

    def __init__(self):
        self._providers: dict[str, AIProvider] = {}
        self._init_providers()

    def _init_providers(self):
        """Initialize all available providers."""
        providers = [
            ("gemini", GeminiProvider),
            ("groq", GroqProvider),
            ("cerebras", CerebrasProvider),
            ("openrouter", OpenRouterProvider),
            ("huggingface", HuggingFaceProvider),
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

        live = len(self._providers)
        logger.info(f"Router  │ {live}/{len(providers)} providers live (minimum required: {MIN_REQUIRED_PROVIDERS})")
        if live < MIN_REQUIRED_PROVIDERS:
            logger.error(
                f"Router  │ ⚠ Only {live} provider(s) available. "
                f"Assembly requires at least {MIN_REQUIRED_PROVIDERS}. "
                f"Add more API keys to .env."
            )

    def get_available_providers(self) -> list[str]:
        """Return names of providers with valid credentials."""
        return list(self._providers.keys())

    def get_live_count(self) -> int:
        """Return the number of currently live providers."""
        return len(self._providers)

    def _enforce_minimum(self):
        """Raise an error if fewer than 3 providers are live."""
        live = len(self._providers)
        if live < MIN_REQUIRED_PROVIDERS:
            available = ", ".join(self._providers.keys()) if self._providers else "none"
            raise RuntimeError(
                f"Assembly requires at least {MIN_REQUIRED_PROVIDERS} AI providers to be live. "
                f"Currently only {live} available ({available}). "
                f"Please add more API keys to your .env file."
            )

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
        - Solver/Analyst → strongest reasoning (Gemini 2.5 Flash, Cerebras 70b)
        - Researcher → good comprehension (Gemini Flash, Groq, HuggingFace)
        - Critic → strong reasoning (Cerebras 70b, Gemini 2.5 Flash)
        - Synthesizer → good writing (Gemini Flash, Groq, Cerebras)
        - Short time budgets → prefer fast/low-latency (Groq, Cerebras)
        """

        self._enforce_minimum()

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

        # For tight time budgets, prefer fast models (Groq & Cerebras are ultra-fast)
        if time_budget_minutes <= 3:
            return [
                ("groq", "llama-3.3-70b-versatile"),
                ("cerebras", "llama-3.3-70b"),
                ("gemini", "gemini-2.0-flash"),
                ("openrouter", "meta-llama/llama-3.1-8b-instruct:free"),
                ("huggingface", "meta-llama/Meta-Llama-3-8B-Instruct"),
            ]

        if agent_type == "solver":
            if problem_type in ("math", "coding"):
                return [
                    ("gemini", "gemini-2.5-flash"),
                    ("cerebras", "llama-3.3-70b"),
                    ("groq", "llama-3.3-70b-versatile"),
                    ("openrouter", "meta-llama/llama-3.1-70b-instruct"),
                    ("huggingface", "meta-llama/Meta-Llama-3-8B-Instruct"),
                ]
            else:
                return [
                    ("gemini", "gemini-2.0-flash"),
                    ("cerebras", "llama-3.3-70b"),
                    ("groq", "llama-3.3-70b-versatile"),
                    ("openrouter", "meta-llama/llama-3.1-8b-instruct:free"),
                    ("huggingface", "meta-llama/Meta-Llama-3-8B-Instruct"),
                ]

        elif agent_type == "researcher":
            return [
                ("gemini", "gemini-2.0-flash"),
                ("groq", "llama-3.1-8b-instant"),
                ("huggingface", "meta-llama/Meta-Llama-3-8B-Instruct"),
                ("cerebras", "llama-3.1-8b"),
                ("openrouter", "meta-llama/llama-3.1-8b-instruct:free"),
            ]

        elif agent_type == "critic":
            if complexity == "high":
                return [
                    ("cerebras", "llama-3.3-70b"),
                    ("gemini", "gemini-2.5-flash"),
                    ("groq", "llama-3.3-70b-versatile"),
                    ("openrouter", "meta-llama/llama-3.1-70b-instruct"),
                    ("huggingface", "meta-llama/Meta-Llama-3-8B-Instruct"),
                ]
            return [
                ("cerebras", "llama-3.3-70b"),
                ("gemini", "gemini-2.0-flash"),
                ("groq", "llama-3.3-70b-versatile"),
                ("openrouter", "meta-llama/llama-3.1-8b-instruct:free"),
                ("huggingface", "meta-llama/Meta-Llama-3-8B-Instruct"),
            ]

        elif agent_type == "synthesizer":
            return [
                ("gemini", "gemini-2.0-flash"),
                ("groq", "llama-3.3-70b-versatile"),
                ("cerebras", "llama-3.3-70b"),
                ("openrouter", "meta-llama/llama-3.1-8b-instruct:free"),
                ("huggingface", "meta-llama/Meta-Llama-3-8B-Instruct"),
            ]

        # Default fallback
        return [
            ("gemini", "gemini-2.0-flash"),
            ("groq", "llama-3.1-8b-instant"),
            ("cerebras", "llama-3.3-70b"),
            ("openrouter", "meta-llama/llama-3.1-8b-instruct:free"),
            ("huggingface", "meta-llama/Meta-Llama-3-8B-Instruct"),
        ]

    def route_for_planning(self) -> ModelAssignment:
        """Route specifically for the Planner (problem classification)."""
        self._enforce_minimum()

        routing = [
            ("gemini", "gemini-2.0-flash"),
            ("groq", "llama-3.3-70b-versatile"),
            ("cerebras", "llama-3.3-70b"),
            ("openrouter", "meta-llama/llama-3.1-8b-instruct:free"),
            ("huggingface", "meta-llama/Meta-Llama-3-8B-Instruct"),
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

