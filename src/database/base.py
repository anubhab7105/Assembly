"""
Assembly — Database Engine & Session

Supports both SQLite (local dev) and PostgreSQL (Supabase production).
Auto-detects the database type from DATABASE_URL.
"""

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, declarative_base, Session
from typing import Generator

from src.core.config import settings
from src.core.logging_config import logger

# ── Engine ───────────────────────────────────────────────────────────
# Auto-detect database type from URL and apply appropriate settings

_connect_args = {}
_engine_kwargs = {}

if settings.is_postgres:
    # PostgreSQL (Supabase) — production settings
    _engine_kwargs = {
        "pool_size": 5,
        "max_overflow": 10,
        "pool_pre_ping": True,       # Verify connections before use
        "pool_recycle": 300,          # Recycle connections every 5 min
        "echo": False,
    }
    logger.info("Database │ Using PostgreSQL (Supabase)")
else:
    # SQLite — local development
    _connect_args = {"check_same_thread": False}
    _engine_kwargs = {
        "echo": settings.debug,
    }
    logger.info("Database │ Using SQLite (local)")

engine = create_engine(
    settings.database_url,
    connect_args=_connect_args,
    **_engine_kwargs,
)

# ── Session Factory ──────────────────────────────────────────────────
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# ── Base Class ───────────────────────────────────────────────────────
Base = declarative_base()


def init_db():
    """Create all tables. Called on application startup."""
    from src.database import models  # noqa: F401 — import to register models
    Base.metadata.create_all(bind=engine)
    logger.info("Database │ Tables created/verified")


def get_db() -> Generator[Session, None, None]:
    """FastAPI dependency that yields a database session."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
