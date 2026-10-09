"""
Assembly — Application Configuration

Loads all environment variables via Pydantic Settings.
Supports local development (SQLite) and production (Supabase PostgreSQL).
"""

import secrets
from pathlib import Path
from typing import Literal

from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings

# ── Resolve project root (two levels up from this file) ──────────────
BASE_DIR = Path(__file__).resolve().parent.parent.parent

DESKTOP_TOKEN = secrets.token_hex(32)


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
    desktop_token: str = DESKTOP_TOKEN

    # ── Frontend URL (for CORS in production) ────────────────────────
    frontend_url: str = ""  # e.g. "https://assembly-frontend.vercel.app"

    # ── Security ─────────────────────────────────────────────────────
    # SecretStr: repr/str show '**********'. Reveal only at the call site.
    jwt_secret_key: SecretStr = Field(default=SecretStr(""))
    jwt_algorithm: str = "HS256"
    jwt_access_token_expire_minutes: int = 1440  # 24 hours
    # Dedicated HMAC salt for quota fingerprinting (must not be the JWT key).
    # Set QUOTA_SALT in .env or environment. Generated from secrets.token_hex(32)
    # if not provided (safe for dev; set explicitly in production).
    quota_salt: SecretStr = Field(default=SecretStr(""))

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

    # ── Reasoning-token reserve for pre-send tpm leases ────────────────
    # Reasoning/thinking tokens bill against per-minute token windows but
    # are only reported AFTER the call, so the quota lease reserves this
    # measured average up front (fail-safe direction: over-reserving only
    # waits, under-reserving trips 429s). Measured on live runs:
    # OpenRouter nemotron critic calls reported 294–1196 reasoning tokens;
    # Gemini reported 0. Re-measure with the per-stage stats when the
    # benchmark grows the sample.
    tokens_reasoning_reserve: int = 700

    # ── Per-stage measured token usage (replaces the AVG_TOKENS_PER_CALL=2000
    # guess from feat/per-model-limits) ─────────────────────────────────
    # Measured on a real 5-minute-tier run (see source_run_id/date below).
    # Values are total tokens per LLM call (input + output as reported by
    # the provider; reasoning tokens are included in output/total when the
    # provider reports them, e.g. OpenRouter nemotron reported 294–1196
    # reasoning tokens per critic call; Gemini reported 0).
    # Breakdown (avg in/out/total, successful calls only):
    #   planner:   325/73/398    (n=1, gemini-3.8-flash)
    #   solve:     513/613/1126  (n=2: solver 440/443/883, critic 586/782/1368)
    #   debate:    876/607/1484  (n=3: 791/412/1203, 791/379/1170, 1047/1031/2078)
    #   synthesis: 1043/1202/2245 (n=1, gemini-3.8-flash)
    # Averages drive capacity math (tpm/tpd → calls); p90 drives worst-case
    # preflight. n=1 run (small sample — re-measure after the benchmark).
    # Source run: question "Is React better than Vue for a large
    # cybersecurity platform?", 3 agents (solver/critic/researcher),
    # researcher (groq gpt-oss-20b) failed all calls with
    # "Tool choice is none, but model called a tool" (0 tokens, excluded
    # from averages); no adversarial round triggered (consensus never hit
    # the early-agreement tripwire), so adversarial reuses debate values.
    token_stats_source_run_id: str = "debug-5m-001"
    token_stats_source_date: str = "2026-10-09"
    tokens_planner_avg: int = 398
    tokens_planner_p90: int = 398
    tokens_solve_avg: int = 1126
    tokens_solve_p90: int = 1368
    tokens_debate_avg: int = 1484
    tokens_debate_p90: int = 2078
    tokens_adversarial_avg: int = 1484
    tokens_adversarial_p90: int = 2078
    tokens_synthesis_avg: int = 2245
    tokens_synthesis_p90: int = 2245

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
        if self.app_mode == "desktop":
            import platformdirs
            data_dir = Path(platformdirs.user_data_dir("Assembly", "Assembly"))
            data_dir.mkdir(parents=True, exist_ok=True)
            return f"sqlite:///{data_dir / 'assembly.db'}"

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
