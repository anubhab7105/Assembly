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
    openai_api_key: str = ""
    gemini_api_key: str = ""
    groq_api_key: str = ""

    # ── Default Models ───────────────────────────────────────────────
    openai_default_model: str = "gpt-4o-mini"
    gemini_default_model: str = "gemini-2.0-flash"
    groq_default_model: str = "llama-3.1-8b-instant"

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
            "openai": self.openai_api_key,
            "gemini": self.gemini_api_key,
            "groq": self.groq_api_key,
        }
        key = key_map.get(provider, "")
        return bool(key) and not key.startswith("sk-your") and not key.startswith("your-") and not key.startswith("gsk_your")


# ── Singleton ────────────────────────────────────────────────────────
settings = Settings()
