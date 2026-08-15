"""
Assembly — Multi-Agent AI Consensus Platform

FastAPI application entry point.
"""

import sys
import os
from pathlib import Path

# Ensure the project root is on the Python path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse

from src.database.base import init_db
from src.api.auth import router as auth_router
from src.api.conversations import router as conversations_router
from src.api.executions import router as executions_router
from src.core.config import settings
from src.core.logging_config import logger


# ═════════════════════════════════════════════════════════════════════
# Application
# ═════════════════════════════════════════════════════════════════════

app = FastAPI(
    title="Assembly",
    description="Multi-Agent AI Consensus Platform",
    version="0.1.0",
)

# ── CORS ─────────────────────────────────────────────────────────────
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── API Routes ───────────────────────────────────────────────────────
app.include_router(auth_router)
app.include_router(conversations_router)
app.include_router(executions_router)

# ── Static Files (Frontend) ─────────────────────────────────────────
STATIC_DIR = Path(__file__).parent / "static"
if STATIC_DIR.exists():
    app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")


@app.get("/")
async def serve_frontend():
    """Serve the main frontend page."""
    index_path = STATIC_DIR / "index.html"
    if index_path.exists():
        return FileResponse(str(index_path))
    return {"message": "Assembly API is running. Frontend not found at /static/index.html"}


@app.get("/health")
async def health_check():
    """Health check endpoint."""
    return {
        "status": "healthy",
        "app": settings.app_name,
        "env": settings.app_env,
    }


# ── Startup ──────────────────────────────────────────────────────────
@app.on_event("startup")
async def startup():
    """Initialize database on startup."""
    logger.info("====================================================")
    logger.info("  Assembly -- Multi-Agent AI Consensus Platform")
    logger.info("====================================================")
    init_db()
    logger.info("Database | Initialized")
    logger.info(f"Server   | Running on http://{settings.host}:{settings.port}")
    logger.info("====================================================")


# ── Run ──────────────────────────────────────────────────────────────
if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "src.main:app",
        host=settings.host,
        port=settings.port,
        reload=settings.debug,
    )
