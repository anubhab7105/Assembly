"""
Assembly — Database Engine & Session

Supports both SQLite (local dev) and PostgreSQL (Supabase production).
Auto-detects the database type from DATABASE_URL.
"""

from collections.abc import Generator

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, declarative_base, sessionmaker

from src.core.config import settings
from src.core.logging_config import logger

# ── Engine ───────────────────────────────────────────────────────────
# Auto-detect database type from URL and apply appropriate settings

_db_url = settings.effective_database_url
_connect_args = {}
_engine_kwargs = {}

if settings.is_postgres:
    # PostgreSQL (Supabase) — production settings
    _engine_kwargs = {
        "pool_size": 5,
        "max_overflow": 10,
        "pool_pre_ping": True,       # Verify connections before use
        "pool_recycle": 300,          # Recycle connections every 5 min
        "pool_timeout": 30,           # Wait up to 30s for a connection
        "echo": False,
    }
    # Supabase requires SSL; connect_args passes through to psycopg2
    _connect_args = {"sslmode": "require", "connect_timeout": 10}
    logger.info("Database │ Using PostgreSQL (Supabase)")
else:
    # SQLite — local development
    _connect_args = {"check_same_thread": False}
    _engine_kwargs = {
        "echo": settings.debug,
    }
    logger.info("Database │ Using SQLite (local)")

engine = create_engine(
    _db_url,
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

    if settings.app_mode in ("dev", "desktop"):
        db = SessionLocal()
        from src.database.models import User
        if not db.query(User).filter(User.id == "local-dev-user").first():
            db.add(
                User(
                    id="local-dev-user",
                    email="local@dev.local",
                    name="Local Dev User",
                    hashed_password="not-used",
                )
            )
            db.commit()
        db.close()

    logger.info("Database │ Tables created/verified")


def get_db() -> Generator[Session, None, None]:
    """FastAPI dependency that yields a database session."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
