"""
Assembly — Application Configuration

Loads all environment variables via Pydantic Settings.
"""

import os
from pathlib import Path
from pydantic_settings import BaseSettings
from pydantic import Field

# ── Resolve project root (two levels up from this file) ──────────────
BASE_DIR = Path(__file__).resolve().parent.parent.parent


class Settings(BaseSettings):
    """Central configuration loaded from .env file."""

    # ── Application ──────────────────────────────────────────────────
    app_name: str = "Assembly"
    app_env: str = "development"
    debug: bool = True
    host: str = "0.0.0.0"
    port: int = 8000

    # ── Security ─────────────────────────────────────────────────────
    jwt_secret_key: str = "change-me-to-a-random-secret-key-at-least-32-chars"
    jwt_algorithm: str = "HS256"
    jwt_access_token_expire_minutes: int = 1440  # 24 hours

    # ── Database ─────────────────────────────────────────────────────
    database_url: str = Field(
        default=f"sqlite:///{BASE_DIR / 'assembly.db'}",
        description="SQLAlchemy database URL",
    )

    # ── AI Provider API Keys ─────────────────────────────────────────
    gemini_api_key: str = ""
    groq_api_key: str = ""
    cerebras_api_key: str = ""
    openrouter_api_key: str = ""
    huggingface_api_key: str = ""

    # ── Default Models ───────────────────────────────────────────────
    gemini_default_model: str = "gemini-2.0-flash"
    groq_default_model: str = "llama-3.1-8b-instant"
    cerebras_default_model: str = "llama-3.3-70b"
    openrouter_default_model: str = "meta-llama/llama-3.1-8b-instruct:free"
    huggingface_default_model: str = "meta-llama/Meta-Llama-3-8B-Instruct"

    # ── Research / Web Search ────────────────────────────────────────
    tavily_api_key: str = ""

    # ── Budget Defaults ──────────────────────────────────────────────
    max_tokens_per_execution: int = 100_000
    max_searches_per_execution: int = 20

    model_config = {
        "env_file": str(BASE_DIR / ".env"),
        "env_file_encoding": "utf-8",
        "extra": "ignore",
    }

    @property
    def is_production(self) -> bool:
        return self.app_env == "production"

    def has_provider(self, provider: str) -> bool:
        """Check if an API key is configured for a provider."""
        key_map = {
            "gemini": self.gemini_api_key,
            "groq": self.groq_api_key,
            "cerebras": self.cerebras_api_key,
            "openrouter": self.openrouter_api_key,
            "huggingface": self.huggingface_api_key,
        }
        key = key_map.get(provider, "")
        # Reject placeholder values
        placeholders = ("sk-your", "your-", "gsk_your", "hf_your", "csk_your")
        return bool(key) and not any(key.startswith(p) for p in placeholders)


# ── Singleton ────────────────────────────────────────────────────────
settings = Settings()
