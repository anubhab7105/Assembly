"""Assembly — stateless web run (POST /api/run, SSE).

Web mode stores nothing: no database file, no disk writes. Runs live in
an in-memory registry with a TTL and global + per-IP concurrency caps. Keys,
questions and answers are held in memory for the run only and never
stored; logs carry metadata (run prefix, tier, timings, counts) only.
"""

import asyncio
import json
import time
import uuid
from dataclasses import dataclass, field

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import JSONResponse, StreamingResponse

from src.api.request_context import (
    _diversity_is_blocked,
    _filtered_router,
    build_request_context,
    diversity_payload,
)
from src.core.config import settings
from src.core.logging_config import logger
from src.core.rate_limit import (
    MAX_RUNS_PER_IP,
    check_rate_limit,
    client_ip,
    count_invalid_request,
)
from src.database.schemas import RunRequest
from src.orchestration.capacity import KeyBudget, heuristic_suggestion, plan_capacity
from src.providers.quota import get_limiter

router = APIRouter(prefix="/api/run", tags=["run"])

#: Machine-readable code for "no usable model family" rejections.
BLOCKED_CODE = "blocked_no_usable_keys"

#: Minimum distinct model families for a healthy team (mirrors catalog).
MINIMUM_FAMILIES = 3


@dataclass
class _RunEntry:
    run_id: str
    created_at: float
    task: asyncio.Task | None = None
    queue: asyncio.Queue = field(default_factory=asyncio.Queue)
    done: bool = False
    usage: list[dict] = field(default_factory=list)
    #: Peer IP owning the run (per-IP concurrency cap; names only, no keys).
    ip: str = ""


_runs: dict[str, _RunEntry] = {}
_runs_lock = asyncio.Lock()


def _now() -> float:
    return time.monotonic()


async def _sweep_expired() -> None:
    ttl = settings.run_ttl_seconds
    now = _now()
    expired = [rid for rid, e in _runs.items() if now - e.created_at > ttl]
    for rid in expired:
        entry = _runs.pop(rid, None)
        if entry is not None and entry.task is not None and not entry.task.done():
            entry.task.cancel()


async def _count_invalid_or_429(ip: str) -> JSONResponse | None:
    """Record a validation failure, or 429 JSON when its budget is spent."""
    try:
        await count_invalid_request(ip)
    except HTTPException as exc:
        if exc.status_code == 429:
            return JSONResponse(
                status_code=429,
                content={"detail": "Too many invalid requests; try again later."},
            )
        raise
    return None




async def _execute_run(
    run_id: str,
    question: str,
    tier: int,
    provider_keys: dict[str, str],
    allowed: set[str],
    pins: dict[str, str],
    usage_snapshot: list[dict],
    entry: _RunEntry,
    search_keys: dict[str, str] | None = None,
    router_override=None,
) -> None:
    """Run the orchestrator, forwarding recorder events into the SSE queue."""
    from src.orchestration.orchestrator import Orchestrator

    limiter = get_limiter()
    limiter.set_usage_snapshot(usage_snapshot or [])
    if router_override is None:
        router_override = _filtered_router(provider_keys, allowed, pins)
    orch = Orchestrator()
    # Use the per-run router (keys + selection) instead of the shared one.
    orch.router = router_override  # type: ignore[assignment]

    async def on_progress(event: dict) -> None:
        await entry.queue.put(dict(event))

    result_status = "failed"
    usage: list[dict] = []
    try:
        result = await orch.execute(
            execution_id=run_id,
            question=question,
            time_budget_minutes=tier,
            on_progress=on_progress,
            provider_keys=provider_keys or None,
            search_keys=search_keys,
            router_override=router_override,
        )
        result_status = result.status
        # Updated usage counters (counts only, never keys).
        usage = [
            {
                "provider": str(u.get("provider", "")),
                "model": str(u.get("model", "")),
                "count": int(u.get("count", 0) or 0),
                "tokens": int(u.get("tokens", 0) or 0),
            }
            for u in (usage_snapshot or [])
        ]
        usage.append(
            {
                "provider": "run",
                "model": "",
                "count": 1,
                "tokens": int(result.total_tokens or 0),
            }
        )
        entry.usage = usage
        await entry.queue.put(
            {
                "event_type": "run.finished",
                "run_id": run_id,
                "status": result_status,
                "usage": usage,
            }
        )
    except asyncio.CancelledError:
        await entry.queue.put(
            {"event_type": "run.finished", "run_id": run_id, "status": "cancelled"}
        )
    except Exception:  # noqa: BLE001 — run must finish as an event, not a crash
        logger.error("Run     │ background run failed")
        await entry.queue.put(
            {"event_type": "run.finished", "run_id": run_id, "status": "failed"}
        )
    finally:
        entry.done = True
        await entry.queue.put(None)  # type: ignore[arg-type] — SSE terminator
        limiter.set_usage_snapshot([])


@router.post("", response_class=StreamingResponse)
async def start_run(req: RunRequest, request: Request):
    """Stream a full run as SSE. Cancels on disconnect. Stateless."""
    ip = client_ip(request)
    # Validation first: a request that fails validation counts against
    # the looser invalid budget, never against the 5/min run budget.
    question = (req.question or "").strip()
    if not question:
        limited = await _count_invalid_or_429(ip)
        return limited if limited is not None else JSONResponse(status_code=422, content={"detail": "Invalid request."})
    if len(question) > settings.max_question_chars:
        limited = await _count_invalid_or_429(ip)
        return limited if limited is not None else JSONResponse(status_code=422, content={"detail": "Invalid request."})
    if req.time_budget_minutes not in (3, 5, 10, 15):
        limited = await _count_invalid_or_429(ip)
        return limited if limited is not None else JSONResponse(status_code=422, content={"detail": "Invalid request."})
    if len(req.provider_keys or {}) > 20:
        limited = await _count_invalid_or_429(ip)
        return limited if limited is not None else JSONResponse(status_code=422, content={"detail": "Invalid request."})
    await check_rate_limit(
        f"ip:{ip}", "run", settings.rate_limit_run_per_min_per_ip, 60
    )
    await _sweep_expired()

    # One shared per-request context for keys, selection, and quota, so
    # the diversity verdict here and the router used below cannot diverge.
    ctx = build_request_context(
        dict(req.provider_keys or {}),
        dict(req.search_keys) if req.search_keys is not None else None,
        list(req.model_selection.selected or []),
        dict(req.model_selection.pins or {}),
        [u.model_dump() for u in (req.usage_snapshot or [])],
    )
    allowed, pins = ctx.allowed, ctx.pins

    # No usable model family: refuse before streaming or spending quota.
    if _diversity_is_blocked(ctx.router, allowed):
        return JSONResponse(
            status_code=400,
            content={
                "code": BLOCKED_CODE,
                "detail": (
                    "No usable model families. Add keys for at least "
                    f"{MINIMUM_FAMILIES} model families (2 work with a "
                    "warning)."
                ),
                "minimum_families": MINIMUM_FAMILIES,
            },
        )

    # Capacity check with max(client snapshot, server memory). Advisory:
    # only an actually-infeasible verdict blocks; errors fail open.
    try:
        limiter = get_limiter()
        keys = [
            KeyBudget(
                provider=e.get("provider", "unknown"),
                rpm_limit=e.get("rpm_limit"),
                rpd_remaining=e.get("rpd_remaining"),
                tpm_limit=e.get("tpm_limit"),
                tpd_remaining=e.get("tpd_remaining"),
            )
            for e in (ctx.quota_snapshot or [])
        ]
        if keys:
            plan = plan_capacity(
                keys,
                req.time_budget_minutes,
                heuristic_suggestion(question),
                usage_snapshot=[u.model_dump() for u in (req.usage_snapshot or [])],
            )
            if not plan.feasible:
                limiter.set_usage_snapshot([])
                return JSONResponse(
                    status_code=429,
                    content={"detail": "Tier not feasible with current quota."},
                )
    except Exception as exc:  # noqa: BLE001 — capacity advisory, fail open
        logger.debug(f"Run     │ capacity check skipped: {exc}")

    async with _runs_lock:
        active = sum(1 for e in _runs.values() if not e.done)
        if active >= settings.max_concurrent_runs:
            return JSONResponse(
                status_code=429, content={"detail": "Server busy, try again later."}
            )
        ip_active = sum(1 for e in _runs.values() if not e.done and e.ip == ip)
        if ip_active >= MAX_RUNS_PER_IP:
            return JSONResponse(
                status_code=429,
                content={
                    "detail": (
                        f"Concurrent execution limit reached ({MAX_RUNS_PER_IP}). "
                        "Wait for your current run to finish."
                    )
                },
            )
        run_id = f"run-{uuid.uuid4().hex[:12]}"
        entry = _RunEntry(run_id=run_id, created_at=_now(), ip=ip)
        _runs[run_id] = entry

    # Family-diversity gate for this run's keys + selection (metadata only).
    run_diversity = diversity_payload(ctx.router, allowed)

    await entry.queue.put(
        {
            "event_type": "run.started",
            "run_id": run_id,
            "diversity": run_diversity,
        }
    )

    logger.info(
        f"Run     │ start tier={req.time_budget_minutes} "
        f"models={len(allowed) or 'auto'}"
    )
    entry.task = asyncio.create_task(
        _execute_run(
            run_id,
            question,
            req.time_budget_minutes,
            dict(req.provider_keys or {}),
            allowed,
            pins,
            [u.model_dump() for u in (req.usage_snapshot or [])],
            entry,
            search_keys=(
                dict(req.search_keys) if req.search_keys is not None else None
            ),
            router_override=ctx.router,
        )
    )

    heartbeat = max(5, settings.sse_heartbeat_seconds)

    async def event_stream():  # type: ignore[no-untyped-def]
        try:
            while True:
                try:
                    item = await asyncio.wait_for(entry.queue.get(), timeout=heartbeat)
                except asyncio.TimeoutError:
                    yield ":heartbeat\n\n"
                    continue
                if item is None:
                    break
                yield f"data: {json.dumps(item)}\n\n"
                if isinstance(item, dict) and item.get("event_type") == "run.finished":
                    # Drain terminator then close.
                    try:
                        term = await asyncio.wait_for(entry.queue.get(), timeout=2.0)
                        _ = term
                    except asyncio.TimeoutError:
                        pass
                    break
        except asyncio.CancelledError:
            # Client disconnected: cancel the run (stateless cancel).
            if entry.task is not None and not entry.task.done():
                entry.task.cancel()
            raise
        finally:
            async with _runs_lock:
                _runs.pop(run_id, None)
            logger.info("Run     │ finished")

    return StreamingResponse(event_stream(), media_type="text/event-stream")
