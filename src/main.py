"""
Assembly — Multi-Agent AI Consensus Platform

FastAPI application entry point.
Supports both local development and production deployment (Render).
"""

import os
import re
import sys
from contextlib import asynccontextmanager
from pathlib import Path

# Ensure the project root is on the Python path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from src.api.auth import router as auth_router
from src.api.conversations import router as conversations_router
from src.api.executions import router as executions_router
from src.api.keys import router as keys_router
from src.core.config import settings
from src.core.logging_config import logger
from src.database.base import init_db

# ═════════════════════════════════════════════════════════════════════
# Lifespan (replaces deprecated @app.on_event)
# ═════════════════════════════════════════════════════════════════════

def _mask_db_url(url: str) -> str:
    """Mask credentials in a database URL for safe logging."""
    return re.sub(r"://([^:]+):([^@]+)@", r"://\1:****@", url)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Initialize database on startup."""
    logger.info("====================================================")
    logger.info("  Assembly -- Multi-Agent AI Consensus Platform")
    logger.info("====================================================")
    init_db()
    db_type = "PostgreSQL (Supabase)" if settings.is_postgres else "SQLite (local)"
    logger.info(f"Server   │ Environment: {settings.app_env}")
    logger.info(f"Server   │ CORS origins: {settings.cors_origins}")
    logger.info(f"Server   │ Database: {db_type}")
    logger.info(f"Server   │ DB URL: {_mask_db_url(settings.effective_database_url)}")
    logger.info("====================================================")
    yield
    logger.info("Server   │ Shutting down")


# ═════════════════════════════════════════════════════════════════════
# Application
# ═════════════════════════════════════════════════════════════════════

app = FastAPI(
    title="Assembly",
    description="Multi-Agent AI Consensus Platform",
    version="0.1.0",
    lifespan=lifespan,
)

# ── CORS ─────────────────────────────────────────────────────────────
# In production, lock down to the Vercel frontend URL.
# In development, allow all origins.
cors_origins = settings.cors_origins
allow_all = "*" in cors_origins

app.add_middleware(
    CORSMiddleware,
    allow_origins=cors_origins if not allow_all else ["*"],
    allow_credentials=not allow_all,  # Can't use credentials with wildcard
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.middleware("http")
async def limit_upload_size(request: Request, call_next):
    # 1MB size limit to prevent abuse
    content_length = request.headers.get("content-length")
    if content_length and int(content_length) > 1024 * 1024:
        return JSONResponse(status_code=413, content={"detail": "Request body too large. Maximum size is 1MB."})
    return await call_next(request)

# ── API Routes ───────────────────────────────────────────────────────
app.include_router(auth_router)
app.include_router(conversations_router)
app.include_router(executions_router)
app.include_router(keys_router)


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request, exc: RequestValidationError):
    """Generic 422: FastAPI's default body echoes offending input values,
    which could include submitted keys. Log only shapes server-side
    (masked), reply generic."""
    shapes = [
        {key: error.get(key) for key in ("type", "loc", "msg")} for error in exc.errors()
    ]
    logger.warning("Validation failed: %s", shapes)
    return JSONResponse(status_code=422, content={"detail": "Invalid request."})

# ── Static Files (Frontend — local dev only) ─────────────────────────
# In production, the frontend is served by Vercel separately.
STATIC_DIR = Path(__file__).parent / "static"
if not settings.frontend_url and STATIC_DIR.exists():
    app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")


@app.get("/")
async def serve_frontend():
    """Serve the main frontend page (local dev) or API info (production)."""
    if settings.frontend_url:
        return {
            "message": "Assembly API is running",
            "frontend": settings.frontend_url,
            "docs": "/docs",
        }
    index_path = STATIC_DIR / "index.html"
    if index_path.exists():
        return FileResponse(str(index_path))
    return {"message": "Assembly API is running. Frontend not found at /static/index.html"}


@app.get("/health")
async def health_check():
    """Health check endpoint for Render.
    
    Tests database connectivity and returns service status.
    """
    from sqlalchemy import text

    from src.database.base import SessionLocal
    db_ok = False
    db_type = "postgresql" if settings.is_postgres else "sqlite"
    try:
        db = SessionLocal()
        db.execute(text("SELECT 1"))
        db.close()
        db_ok = True
    except Exception as e:  # noqa: BLE001 — any DB failure means degraded, details stay server-side
        logger.error(f"Health check │ DB connection failed: {e}")

    status = "healthy" if db_ok else "degraded"
    return {
        "status": status,
        "app": settings.app_name,
        "env": settings.app_env,
        "database": {"type": db_type, "connected": db_ok},
    }


# ── Run ──────────────────────────────────────────────────────────────
if __name__ == "__main__":
    import uvicorn

    # Use PORT from environment (Render provides this) or default
    port = int(os.environ.get("PORT", settings.port))

    uvicorn.run(
        "src.main:app",
        host="0.0.0.0",
        port=port,
        reload=settings.debug,
    )
