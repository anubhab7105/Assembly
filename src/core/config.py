"""Assembly — Application Configuration (stateless web + local desktop).

Web mode stores nothing server-side: no database file, no disk writes.
Desktop/dev modes keep a local SQLite file for run history.
"""

import secrets
from pathlib import Path
from typing import Literal

from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings

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
    # Key backend selector: web (per-request keys, stateless) |
    # desktop (OS keyring + local SQLite) | dev (env keys + local SQLite).
    app_mode: Literal["web", "desktop", "dev"] = "dev"
    desktop_token: str = DESKTOP_TOKEN

    # ── Frontend / CORS allow-list ───────────────────────────────────
    # Comma-separated origins also accepted via CORS_ALLOW_LIST.
    frontend_url: str = ""
    cors_allow_list: str = ""

    # ── Stateless run registry (web) ─────────────────────────────────
    run_ttl_seconds: int = 3600
    max_concurrent_runs: int = 20
    sse_heartbeat_seconds: int = 15

    # ── Abuse protection (no accounts) ───────────────────────────────
    max_body_bytes: int = 1024 * 1024
    max_question_chars: int = 2000
    rate_limit_run_per_min_per_ip: int = 5
    rate_limit_preflight_per_min_per_ip: int = 10
    rate_limit_key_test_per_min_per_ip: int = 10

    # ── Quota salt (dedicated HMAC salt for key fingerprinting) ──────
    quota_salt: SecretStr = Field(default=SecretStr(""))

    # ── AI Provider API Keys (dev mode only) ─────────────────────────
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
    def is_web(self) -> bool:
        return self.app_mode == "web"

    @property
    def effective_database_url(self) -> str:
        """Desktop/dev SQLite URL. Web mode has no database — raises."""
        if self.is_web:
            raise RuntimeError("Web mode is stateless: no database URL.")
        import platformdirs

        data_dir = Path(platformdirs.user_data_dir("Assembly", "Assembly"))
        data_dir.mkdir(parents=True, exist_ok=True)
        return f"sqlite:///{data_dir / 'assembly.db'}"

    @property
    def is_production(self) -> bool:
        return self.app_env == "production"

    @property
    def is_postgres(self) -> bool:
        """Postgres/Supabase removed: always False (kept for compat)."""
        return False

    @property
    def cors_origins(self) -> list[str]:
        """Allowed CORS origins. Web: explicit allow-list only."""
        origins: list[str] = []
        if self.frontend_url:
            origins.append(self.frontend_url.rstrip("/") or self.frontend_url)
        if self.cors_allow_list:
            origins.extend(
                o.strip().rstrip("/")
                for o in self.cors_allow_list.split(",")
                if o.strip()
            )
        # Dedupe, preserve order.
        seen: set[str] = set()
        out: list[str] = []
        for o in origins:
            if o and o not in seen:
                seen.add(o)
                out.append(o)
        if out:
            return out
        if self.is_web:
            return []
        return ["*"]

    def has_provider(self, provider: str) -> bool:
        """Check if an API key is configured for a provider (dev only)."""
        key_map = {
            "gemini": self.gemini_api_key,
            "groq": self.groq_api_key,
            "cerebras": self.cerebras_api_key,
            "openrouter": self.openrouter_api_key,
            "huggingface": self.huggingface_api_key,
        }
        raw = key_map.get(provider)
        key = raw.get_secret_value() if isinstance(raw, SecretStr) else (raw or "")
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
