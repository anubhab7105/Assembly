"""Assembly — Database Engine & Session (desktop/dev SQLite only).

Web mode is stateless: no engine, no database file, no disk writes.
Importing this module in web mode must not create any file.
"""

from collections.abc import Generator
from typing import TYPE_CHECKING

from sqlalchemy.orm import Session, declarative_base, sessionmaker

from src.core.config import settings

Base = declarative_base()

_engine = None
SessionLocal = None


def _ensure_engine():  # type: ignore[no-untyped-def]
    """Lazily build the SQLite engine (desktop/dev only)."""
    global _engine, SessionLocal
    if settings.is_web:
        raise RuntimeError("Web mode is stateless: no database available.")
    if _engine is None:
        from sqlalchemy import create_engine

        from src.core.logging_config import logger

        url = settings.effective_database_url
        _engine = create_engine(
            url,
            connect_args={"check_same_thread": False},
            echo=settings.debug,
        )
        SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=_engine)
        logger.info("Database │ Using SQLite (desktop local)")
    return _engine


def init_db() -> None:
    """Create all tables. No-op in web mode (stateless)."""
    if settings.is_web:
        return
    _ensure_engine()
    from src.core.logging_config import logger
    from src.database import models  # noqa: F401 — register models

    assert _engine is not None
    Base.metadata.create_all(bind=_engine)
    logger.info("Database │ Tables created/verified")


def get_db() -> Generator[Session, None, None]:
    """FastAPI dependency (desktop/dev only)."""
    if settings.is_web:
        raise RuntimeError("Web mode is stateless: no database session.")
    _ensure_engine()
    assert SessionLocal is not None
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


if TYPE_CHECKING:
    from sqlalchemy import Engine

    engine: Engine | None = None
else:
    # Eager engine only outside web mode; web import stays file-free.
    try:
        engine = _ensure_engine() if not settings.is_web else None
    except Exception as exc:  # noqa: BLE001 — import must never crash
        from src.core.logging_config import logger as _logger

        _logger.debug(f"Database │ engine deferred: {exc}")
        engine = None
