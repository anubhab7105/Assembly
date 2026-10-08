"""
Assembly — Application Configuration

Loads all environment variables via Pydantic Settings.
Supports local development (SQLite) and production (Supabase PostgreSQL).
"""

from pathlib import Path
from typing import Literal

from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings

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
    # Key backend selector: dev (env keys) | web (per-request keys) |
    # desktop (OS keyring). Env keys refuse to load when app_env=production.
    app_mode: Literal["dev", "web", "desktop"] = "dev"

    # ── Frontend URL (for CORS in production) ────────────────────────
    frontend_url: str = ""  # e.g. "https://assembly-frontend.vercel.app"

    # ── Security ─────────────────────────────────────────────────────
    # SecretStr: repr/str show '**********'. Reveal only at the call site.
    jwt_secret_key: SecretStr = Field(default=SecretStr(""))
    jwt_algorithm: str = "HS256"
    jwt_access_token_expire_minutes: int = 1440  # 24 hours

    # ── Database ─────────────────────────────────────────────────────
    database_url: str = Field(
        default=f"sqlite:///{BASE_DIR / 'assembly.db'}",
        description="Database URL. Use postgresql://... for Supabase, sqlite:///... for local dev.",
    )

    # ── AI Provider API Keys ─────────────────────────────────────────
    gemini_api_key: SecretStr = Field(default=SecretStr(""))
    groq_api_key: SecretStr = Field(default=SecretStr(""))
    cerebras_api_key: SecretStr = Field(default=SecretStr(""))
    openrouter_api_key: SecretStr = Field(default=SecretStr(""))
    huggingface_api_key: SecretStr = Field(default=SecretStr(""))

    # ── Research / Web Search ────────────────────────────────────────
    tavily_api_key: SecretStr = Field(default=SecretStr(""))

    # ── Budget Defaults ──────────────────────────────────────────────
    max_tokens_per_execution: int = 100_000
    max_searches_per_execution: int = 20

    # ── Consensus scoring (docs/WORKFLOW.md section 6) ───────────────
    # Starting weights — tune on the benchmark, never hard-code elsewhere.
    consensus_w_agreement: float = 0.30
    consensus_w_confidence: float = 0.20
    consensus_w_evidence: float = 0.25
    consensus_w_contradiction: float = 0.15
    consensus_w_stability: float = 0.10
    consensus_finalize_threshold: float = 0.85
    consensus_new_info_threshold: float = 0.15
    consensus_contradiction_limit: float = 0.20
    consensus_evidence_floor: float = 0.50

    model_config = {
        "env_file": str(BASE_DIR / ".env"),
        "env_file_encoding": "utf-8",
        "extra": "ignore",
    }

    @property
    def effective_database_url(self) -> str:
        """Return the database URL with common fixes applied.

        Supabase and Heroku sometimes provide `postgres://` which
        SQLAlchemy 2.x does not accept — it requires `postgresql://`.
        """
        url = self.database_url
        if url.startswith("postgres://"):
            url = url.replace("postgres://", "postgresql://", 1)
        return url

    @property
    def is_production(self) -> bool:
        return self.app_env == "production"

    @property
    def is_postgres(self) -> bool:
        """Check if using PostgreSQL (Supabase) vs SQLite."""
        return self.effective_database_url.startswith("postgresql")

    @property
    def cors_origins(self) -> list[str]:
        """Allowed CORS origins based on environment."""
        if self.frontend_url:
            # Production: only allow the specific frontend URL
            origins = [self.frontend_url]
            # Also allow common variations (with/without trailing slash)
            if self.frontend_url.endswith("/"):
                origins.append(self.frontend_url.rstrip("/"))
            else:
                origins.append(self.frontend_url + "/")
            return origins
        # Development: allow all origins
        return ["*"]

    def has_provider(self, provider: str) -> bool:
        """Check if an API key is configured for a provider."""
        key_map = {
            "gemini": self.gemini_api_key,
            "groq": self.groq_api_key,
            "cerebras": self.cerebras_api_key,
            "openrouter": self.openrouter_api_key,
            "huggingface": self.huggingface_api_key,
        }
        raw = key_map.get(provider)
        key = raw.get_secret_value() if isinstance(raw, SecretStr) else (raw or "")
        # Reject placeholder values
        placeholders = (
            "sk-your",
            "your-",
            "gsk_your",
            "hf_your",
            "csk_your",
            "xpl_your",
        )
        return bool(key) and not any(key.startswith(p) for p in placeholders)


# ── Singleton ────────────────────────────────────────────────────────
settings = Settings()
