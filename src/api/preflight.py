"""Assembly — capacity preflight (POST /api/preflight).

One shared per-request context (provider keys, search-key presence, model
selection, usage snapshot) with /api/run, so the verdict and the run
cannot diverge. Keys travel in the request body only (never URLs), stay in
memory only, and are never logged or echoed in validation errors.
"""

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

from src.api.executions import _build_preflight
from src.api.request_context import build_request_context
from src.core.config import settings
from src.core.rate_limit import check_rate_limit
from src.database.schemas import PreflightResponse, RunRequest

router = APIRouter(prefix="/api", tags=["preflight"])


@router.post("/preflight", response_model=PreflightResponse)
async def preflight(req: RunRequest, request: Request):
    """Capacity verdict for this request's keys + selection, without running."""
    ip = request.client.host if request.client else "unknown"
    await check_rate_limit(
        f"ip:{ip}", "preflight", settings.rate_limit_preflight_per_min_per_ip, 60
    )
    question = (req.question or "").strip()
    if not question:
        return JSONResponse(status_code=422, content={"detail": "Invalid request."})
    if len(question) > settings.max_question_chars:
        return JSONResponse(status_code=422, content={"detail": "Invalid request."})
    if req.time_budget_minutes not in (3, 5, 10, 15):
        return JSONResponse(status_code=422, content={"detail": "Invalid request."})
    ctx = build_request_context(
        dict(req.provider_keys or {}),
        dict(req.search_keys) if req.search_keys is not None else None,
        list(req.model_selection.selected or []),
        dict(req.model_selection.pins or {}),
        [u.model_dump() for u in (req.usage_snapshot or [])],
    )
    return _build_preflight(
        question,
        req.time_budget_minutes,
        [u.model_dump() for u in (req.usage_snapshot or [])],
        router_override=ctx.router,
    )
