"""Assembly — Multi-Agent AI Consensus Platform (stateless web + desktop).

Web mode stores nothing server-side. Desktop/dev keep local SQLite.
"""

import os
import signal
import sys
import time
from contextlib import asynccontextmanager
from pathlib import Path

START_TIME = time.time()

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from src.api.catalog import router as catalog_router
from src.api.executions import router as executions_router
from src.api.keys import router as keys_router
from src.api.preflight import router as preflight_router
from src.api.run import router as run_router
from src.core.config import settings
from src.core.logging_config import logger


def require_cors_allow_list() -> None:
    """Refuse production startup without an explicit CORS allow-list.

    Production serves no implicit CORS default (``cors_origins`` is []
    there), so booting without CORS_ALLOW_LIST would silently serve an
    unreachable-or-open API. Raise with the exact variable to set.
    """
    if settings.is_production and not settings.cors_allow_list:
        raise RuntimeError(
            "Production requires CORS_ALLOW_LIST: set it to a comma-separated "
            "list of allowed frontend origins (e.g. "
            "CORS_ALLOW_LIST=https://assembly.example.com)."
        )


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Initialize storage on startup (desktop/dev only)."""
    logger.info("====================================================")
    logger.info("  Assembly -- Multi-Agent AI Consensus Platform")
    logger.info("====================================================")
    require_cors_allow_list()
    if settings.is_web:
        logger.info("Server   │ Mode: web (stateless — no database, no disk writes)")
    else:
        from src.database.base import init_db

        init_db()
        logger.info("Server   │ Mode: desktop/dev (local SQLite)")
    logger.info(f"Server   │ Environment: {settings.app_env}")
    logger.info(f"Server   │ CORS origins: {settings.cors_origins or 'none (same-origin)'}")

    try:
        from src.core.keystore import enforce_web_key_policy

        enforce_web_key_policy()
    except RuntimeError as exc:
        logger.error(f"Server   │ {exc}")
        raise
    try:
        from src.providers.quota import get_quota_salt

        if not get_quota_salt():
            raise RuntimeError("Quota salt misconfigured.")
    except RuntimeError:
        raise
    except Exception as exc:
        raise RuntimeError(f"Quota salt misconfigured: {exc}") from exc
    logger.info("====================================================")

    try:
        from src.providers.config import (
            LimitsNotFilledError,
            load_models_config,
            validate_limits_filled,
        )

        validate_limits_filled(load_models_config())
        logger.info("Server   │ models.yaml limits filled for all enabled models")
    except LimitsNotFilledError as exc:
        # Keep the API online, but the router and catalog mark providers with
        # unknown limits unavailable. Do not pretend quota capacity is known.
        logger.error(
            f"Server   │ Provider routing degraded: {exc}. "
            "Affected providers are not routable until limits are verified."
        )
    except Exception as exc:  # noqa: BLE001 — catalog trouble must not kill boot
        logger.warning(f"Server   │ models.yaml check skipped: {exc}")

    yield
    logger.info("Server   │ Shutting down")

    try:
        from src.api.executions import _orchestrator, _run_tasks

        tasks = list(_run_tasks.items())
        for exec_id, task in tasks:
            logger.info(f"Server   │ Canceling execution {exec_id} for graceful shutdown")
            _orchestrator.request_cancel(exec_id)
            if not task.done():
                task.cancel()
    except Exception:  # noqa: BLE001, S110 — shutdown path must not crash
        pass


app = FastAPI(
    title="Assembly",
    description="Multi-Agent AI Consensus Platform",
    version="0.1.0",
    lifespan=lifespan,
    # Production serves no interactive docs: /docs, /redoc and
    # /openapi.json are dev-only (prevents catalog/schema enumeration).
    docs_url=None if settings.is_production else "/docs",
    redoc_url=None if settings.is_production else "/redoc",
    openapi_url=None if settings.is_production else "/openapi.json",
)

# ── CORS: explicit allow-list in web; open locally ───────────────────
cors_origins = settings.cors_origins
if cors_origins == ["*"]:
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=False,
        allow_methods=["*"],
        allow_headers=["*"],
    )
elif cors_origins:
    app.add_middleware(
        CORSMiddleware,
        allow_origins=cors_origins,
        allow_credentials=False,
        allow_methods=["GET", "POST", "OPTIONS"],
        allow_headers=["Content-Type"],
        max_age=600,
    )


@app.middleware("http")
async def desktop_token_middleware(request: Request, call_next):
    if settings.app_mode == "desktop" and request.url.path not in [
        "/health",
        "/ready",
        "/shutdown",
    ] and not request.url.path.startswith("/ws/"):
        token = request.headers.get("Authorization", "").removeprefix("Bearer ")
        if not token:
            token = request.headers.get("X-Assembly-Token", "")
        if token != settings.desktop_token:
            return JSONResponse(status_code=401, content={"detail": "Unauthorized"})
    return await call_next(request)


@app.middleware("http")
async def limit_upload_size(request: Request, call_next):
    from src.core.rate_limit import client_ip, count_invalid_request

    content_length = request.headers.get("content-length")
    if content_length and int(content_length) > settings.max_body_bytes:
        try:
            await count_invalid_request(client_ip(request))
        except HTTPException as exc:
            if exc.status_code == 429:
                return JSONResponse(
                    status_code=429,
                    content={"detail": "Too many invalid requests; try again later."},
                )
        except Exception:  # noqa: BLE001 — oversized bodies fail closed either way
            pass
        return JSONResponse(status_code=413, content={"detail": "Request body too large."})

    # SSE/WebSocket origin check (web mode with allow-list configured).
    if settings.is_web and settings.cors_origins:
        origin = request.headers.get("origin")
        if origin and request.url.path.startswith(("/api/run", "/api/executions/ws")):
            allowed = [o.rstrip("/") for o in settings.cors_origins]
            if origin.rstrip("/") not in allowed:
                return JSONResponse(status_code=403, content={"detail": "Invalid origin."})

    response = await call_next(request)

    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    response.headers["Strict-Transport-Security"] = "max-age=63072000; includeSubDomains; preload"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Permissions-Policy"] = "camera=(), microphone=(), geolocation=()"
    # API serves JSON/SSE only: lock framing, no active content permissions.
    response.headers["Content-Security-Policy"] = "frame-ancestors 'none'; object-src 'none'; base-uri 'self'"

    return response


# ── API Routes (no auth router, no conversations router) ─────────────
app.include_router(run_router)
app.include_router(preflight_router)
app.include_router(catalog_router)
app.include_router(executions_router)
app.include_router(keys_router)


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request, exc: RequestValidationError):
    """Generic 422: never echo offending input values (may include keys).

    Schema-validation failures count against the looser invalid budget,
    never against any endpoint's run budget.
    """
    from src.core.rate_limit import client_ip, count_invalid_request

    shapes = [{key: error.get(key) for key in ("type", "loc", "msg")} for error in exc.errors()]
    logger.warning("Validation failed: %s", shapes)
    try:
        await count_invalid_request(client_ip(request))
    except HTTPException as budget_exc:
        if budget_exc.status_code == 429:
            return JSONResponse(
                status_code=429,
                content={"detail": "Too many invalid requests; try again later."},
            )
    except Exception:  # noqa: BLE001 — limiter trouble must not break the 422
        pass
    return JSONResponse(status_code=422, content={"detail": "Invalid request."})


from fastapi import WebSocketException
from starlette.exceptions import HTTPException as StarletteHTTPException


@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    """Ensure stack traces and config values are never leaked."""
    if isinstance(exc, (StarletteHTTPException, WebSocketException)):
        raise exc
    logger.error("Unhandled exception: %s", exc, exc_info=True)
    return JSONResponse(status_code=500, content={"detail": "Internal server error."})


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
    """Health check. Web: no DB probe (stateless). Desktop: SQLite probe."""
    if settings.is_web:
        return {
            "status": "healthy",
            "app": settings.app_name,
            "env": settings.app_env,
            "mode": "web-stateless",
            "uptime_seconds": int(time.time() - START_TIME),
        }
    from sqlalchemy import text

    from src.database.base import SessionLocal

    db_ok = False
    try:
        db = SessionLocal()
        db.execute(text("SELECT 1"))
        db.close()
        db_ok = True
    except Exception as e:  # noqa: BLE001 — degraded, details server-side
        logger.error(f"Health check │ DB connection failed: {e}")

    status = "healthy" if db_ok else "degraded"
    return {
        "status": status,
        "app": settings.app_name,
        "env": settings.app_env,
        "mode": settings.app_mode,
        "database": {"type": "sqlite", "connected": db_ok},
        "uptime_seconds": int(time.time() - START_TIME),
    }


@app.get("/ready")
async def ready_check():
    """Liveness/readiness probe."""
    return {
        "status": "ready",
        "uptime_seconds": int(time.time() - START_TIME),
    }


@app.post("/shutdown")
async def shutdown(request: Request):
    """Graceful shutdown for desktop app."""
    if settings.app_mode == "desktop":
        token = request.headers.get("Authorization", "").removeprefix("Bearer ")
        if not token:
            token = request.headers.get("X-Assembly-Token", "")
        if token != settings.desktop_token:
            return JSONResponse(status_code=401, content={"detail": "Unauthorized"})

        logger.info("Server   │ Shutdown requested via API")
        os.kill(os.getpid(), signal.SIGINT)
        return {"detail": "Shutting down"}
    return JSONResponse(status_code=404, content={"detail": "Not found"})


# ── Run ──────────────────────────────────────────────────────────────
if __name__ == "__main__":
    import socket

    import uvicorn

    if settings.app_mode == "desktop":
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.bind(("127.0.0.1", 0))
        port = s.getsockname()[1]
        s.close()

        print(f"ASSEMBLY_PORT={port}")
        print(f"ASSEMBLY_TOKEN={settings.desktop_token}")

        host = "127.0.0.1"
        reload = False

    else:
        port = int(os.environ.get("PORT", settings.port))
        host = "0.0.0.0"
        reload = settings.debug

    uvicorn.run(
        app if getattr(sys, "frozen", False) or not reload else "src.main:app",
        host=host,
        port=port,
        reload=reload,
    )
