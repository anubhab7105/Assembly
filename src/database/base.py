"""
Assembly — Database Engine & Session

SQLite for MVP with synchronous SQLAlchemy (simple, no async driver needed).
"""

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, declarative_base, Session
from typing import Generator

from src.core.config import settings, BASE_DIR

# ── Engine ───────────────────────────────────────────────────────────
# Use SQLite with a file in the project root
DATABASE_URL = f"sqlite:///{BASE_DIR / 'assembly.db'}"

engine = create_engine(
    DATABASE_URL,
    connect_args={"check_same_thread": False},  # Required for SQLite
    echo=settings.debug,
)

# ── Session Factory ──────────────────────────────────────────────────
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# ── Base Class ───────────────────────────────────────────────────────
Base = declarative_base()


def init_db():
    """Create all tables. Called on application startup."""
    from src.database import models  # noqa: F401 — import to register models
    Base.metadata.create_all(bind=engine)


def get_db() -> Generator[Session, None, None]:
    """FastAPI dependency that yields a database session."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
