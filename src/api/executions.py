"""Assembly — Executions API (desktop local history + open preflight).

Web mode is stateless: use POST /api/run (SSE) instead. The persisted
endpoints below serve desktop/dev local history only. No accounts, no
user_id ownership anywhere.
"""

import asyncio
import json
from datetime import datetime, timezone

from fastapi import (
    APIRouter,
    Depends,
    HTTPException,
    Query,
    Request,
    WebSocket,
    WebSocketDisconnect,
    status,
)
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session

from src.api.events import event_to_wire, fetch_events, fetch_latest_seq, persist_event
from src.core.config import settings
from src.core.logging_config import logger
from src.core.rate_limit import check_rate_limit, execution_tracker
from src.database.base import SessionLocal, get_db
from src.database.models import AgentRun, Execution
from src.database.schemas import (
    EventListResponse,
    ExecutionCancelResponse,
    ExecutionRequest,
    ExecutionResponse,
    PlannerSuggestionResponse,
    PreflightResponse,
)
from src.orchestration.capacity import KeyBudget, heuristic_suggestion, plan_capacity
from src.orchestration.orchestrator import Orchestrator
from src.research.sanitize import scan_for_injection, summarize_flags

router = APIRouter(prefix="/api/executions", tags=["executions"])

_ws_connections: dict[str, list[WebSocket]] = {}
_ws_seq: dict[int, int] = {}
_run_tasks: dict[str, asyncio.Task] = {}
MAX_WS_CONNECTIONS_PER_EXEC: int = 20

_orchestrator = Orchestrator()


def _require_desktop() -> None:
    if settings.is_web:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Use POST /api/run in web mode.",
        )


def _build_preflight(
    question: str,
    tier: int,
    snapshot: list[dict],
    router_override=None,
) -> PreflightResponse:
    suggestion = heuristic_suggestion(question)
    router_obj = router_override if router_override is not None else _orchestrator.router
    raw_snapshot = router_obj.quota_snapshot() if hasattr(router_obj, "quota_snapshot") else []
    keys = [
        KeyBudget(
            provider=entry.get("provider", "unknown"),
            rpm_limit=entry.get("rpm_limit"),
            rpd_remaining=entry.get("rpd_remaining"),
            tpm_limit=entry.get("tpm_limit"),
            tpd_remaining=entry.get("tpd_remaining"),
        )
        for entry in raw_snapshot
    ]
    plan = plan_capacity(keys, tier, suggestion, usage_snapshot=snapshot)
    warnings = list(plan.warnings)
    for entry in raw_snapshot:
        if (entry.get("cooldown_seconds") or 0) > 0:
            warnings.append(
                f"Provider {entry.get('provider')} is cooling down "
                f"({entry.get('cooldown_seconds')}s); "
                "it may be unavailable at execution start."
            )
            break

    from src.orchestration.capacity import (
        TIER_MAX_AGENTS,
        TIER_MAX_ROUNDS,
        cost_of_plan,
    )
    from src.orchestration.core_roles import (
        ensure_core_roles,
        final_roles_with_synthesizer,
        single_family_warning,
    )
    from src.providers.router import DiversityGateResponse

    # FR-2: final team roles after the core-role guarantee (+ synthesizer).
    team_roles = list(suggestion.roles)
    team_roles, _core_adjust = ensure_core_roles(
        team_roles, TIER_MAX_AGENTS.get(tier, 3)
    )
    final_roles = final_roles_with_synthesizer(team_roles)
    families_for_warning = (
        router_obj.available_families()
        if hasattr(router_obj, "available_families")
        else []
    )
    fam_warning = single_family_warning(families_for_warning)
    if fam_warning and fam_warning not in warnings:
        warnings.append(fam_warning)

    ceiling_agents = TIER_MAX_AGENTS.get(plan.feasible_tier, plan.agents)
    ceiling_rounds = TIER_MAX_ROUNDS.get(plan.feasible_tier, plan.rounds)
    # Median = planned rounds (consensus typically stops early here);
    # worst = ceiling rounds (consensus never reached, every round runs).
    expected_calls_median = plan.estimated_calls
    expected_calls_worst = cost_of_plan(
        plan.agents, max(plan.rounds, ceiling_rounds), plan.search_budget
    )
    try:
        gate = (
            router_obj.diversity_gate()
            if hasattr(router_obj, "diversity_gate")
            else None
        )
        diversity = (
            DiversityGateResponse(**gate.to_dict())  # type: ignore[arg-type]
            if gate is not None
            else DiversityGateResponse()
        )
    except Exception:  # noqa: BLE001 — preflight must answer, never 500
        diversity = DiversityGateResponse()

    return PreflightResponse(
        question=question,
        requested_tier=tier,
        feasible_tier=plan.feasible_tier,
        feasible=plan.feasible,
        downgraded=plan.downgraded,
        agents=plan.agents,
        rounds=plan.rounds,
        search_budget=plan.search_budget,
        estimated_calls=plan.estimated_calls,
        estimated_seconds=round(plan.estimated_seconds, 1),
        affordable_calls=plan.affordable_calls,
        synth_reserve_seconds=round(plan.synth_reserve_seconds, 1),
        warnings=warnings,
        explanation=plan.explanation,
        planner_suggestion=PlannerSuggestionResponse(
            roles=list(suggestion.roles),
            complexity=suggestion.complexity,
            needs_research=suggestion.needs_research,
            estimated_rounds=suggestion.estimated_rounds,
        ),
        usable_keys=len(keys),
        providers=[k.provider for k in keys],
        families=router_obj.available_families()
        if hasattr(router_obj, "available_families")
        else [],
        ceiling_agents=ceiling_agents,
        ceiling_rounds=ceiling_rounds,
        expected_calls_median=expected_calls_median,
        expected_calls_worst=expected_calls_worst,
        expected_tokens_median=plan.estimated_tokens_median,
        expected_tokens_worst=plan.estimated_tokens_worst,
        diversity=diversity,
        final_roles=final_roles,
    )


@router.post("/", response_model=ExecutionResponse)
async def create_execution(req: ExecutionRequest, request: Request, db: Session = Depends(get_db)):
    """Desktop/dev only: submit a question, track locally. Web uses /api/run."""
    _require_desktop()
    ip = request.client.host if request.client else "unknown"
    await check_rate_limit(f"ip:{ip}", "create_execution", 5, 60)
    if req.time_budget_minutes not in (3, 5, 10, 15):
        raise HTTPException(status_code=400, detail="Time budget must be 3, 5, 10, or 15 minutes.")
    if len(req.question) > settings.max_question_chars:
        raise HTTPException(status_code=422, detail="Invalid request.")

    question_flags = scan_for_injection(req.question)
    if question_flags:
        logger.warning(f"Exec    | Injection markers in question: {summarize_flags(question_flags)}")

    execution = Execution(
        question=req.question,
        time_budget_minutes=req.time_budget_minutes,
        status="pending",
        started_at=datetime.now(timezone.utc),
    )
    db.add(execution)
    db.commit()
    db.refresh(execution)

    await execution_tracker.acquire(ip)
    try:
        _run_tasks[execution.id] = asyncio.get_event_loop().create_task(
            _run_execution(
                execution.id,
                req.question,
                req.time_budget_minutes,
                req.provider_keys,
                search_keys=req.search_keys,
                is_demo=req.is_demo,
            )
        )
        return ExecutionResponse.model_validate(execution)
    except Exception:
        await execution_tracker.release(ip)
        raise


@router.post("/{execution_id}/cancel", response_model=ExecutionCancelResponse)
async def cancel_execution(execution_id: str, db: Session = Depends(get_db)):
    """Request cancellation of a running execution (desktop/dev)."""
    _require_desktop()
    execution = db.query(Execution).filter(Execution.id == execution_id).first()
    if not execution:
        raise HTTPException(status_code=404, detail="Execution not found.")
    if execution.status in ("completed", "failed", "failed_partial", "cancelled"):
        return ExecutionCancelResponse(id=execution_id, status=execution.status)
    _orchestrator.request_cancel(execution_id)
    task = _run_tasks.get(execution_id)
    if task is not None and not task.done():
        _cancel_task(task)
        logger.info(f"Exec    │ Cancel delivered to {execution_id[:8]}...")
    return ExecutionCancelResponse(id=execution_id, status="cancelling")


@router.get("/preflight")
async def preflight() -> JSONResponse:
    """Gone: use POST /api/preflight (per-request keys in the body)."""
    return JSONResponse(
        status_code=410,
        content={"detail": "Gone: use POST /api/preflight.", "use": "POST /api/preflight"},
    )


@router.post("/preflight")
async def preflight_post() -> JSONResponse:
    """Gone: use POST /api/preflight (per-request keys in the body)."""
    return JSONResponse(
        status_code=410,
        content={"detail": "Gone: use POST /api/preflight.", "use": "POST /api/preflight"},
    )


@router.get("/{execution_id}", response_model=ExecutionResponse)
async def get_execution(execution_id: str, db: Session = Depends(get_db)):
    """Get execution status and result (desktop/dev local history)."""
    _require_desktop()
    execution = db.query(Execution).filter(Execution.id == execution_id).first()
    if not execution:
        raise HTTPException(status_code=404, detail="Execution not found.")
    return ExecutionResponse.model_validate(execution)


@router.get("/{execution_id}/events", response_model=EventListResponse)
async def list_events(
    execution_id: str,
    after_seq: int = Query(0, ge=0),
    limit: int = Query(500, ge=1, le=2000),
    db: Session = Depends(get_db),
):
    """Replayable event log (desktop/dev local history)."""
    _require_desktop()
    execution = db.query(Execution).filter(Execution.id == execution_id).first()
    if not execution:
        raise HTTPException(status_code=404, detail="Execution not found.")
    rows = fetch_events(db, execution_id, after_seq=after_seq, limit=limit)
    return EventListResponse(
        events=[event_to_wire(row) for row in rows],
        latest_seq=fetch_latest_seq(db, execution_id),
    )


# ═════════════════════════════════════════════════════════════════════
# WebSocket — Real-time Progress (desktop/dev runs; web uses SSE)
# ═════════════════════════════════════════════════════════════════════


@router.websocket("/ws/{execution_id}")
async def websocket_progress(websocket: WebSocket, execution_id: str):
    """Desktop/dev progress socket. Origin-checked; desktop needs token."""
    await websocket.accept()

    origin = websocket.headers.get("origin")
    allowed = settings.cors_origins
    if allowed and origin and origin.rstrip("/") not in [o.rstrip("/") for o in allowed]:
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION, reason="Invalid Origin")
        return

    if settings.app_mode == "desktop":
        try:
            data = await asyncio.wait_for(websocket.receive_text(), timeout=5.0)
            msg = json.loads(data)
            if msg.get("type") != "auth" or msg.get("token") != settings.desktop_token:
                await websocket.close(code=4001, reason="Authentication failed")
                return
        except Exception:
            await websocket.close(code=4001, reason="Authentication failed")
            return
    else:
        # Web/dev: no token in URL; consume one optional hello message.
        try:
            await asyncio.wait_for(websocket.receive_text(), timeout=2.0)
        except Exception:
            pass

    if settings.is_web:
        await websocket.close(code=4004, reason="Use POST /api/run in web mode")
        return

    db = SessionLocal()
    try:
        execution = db.query(Execution).filter(Execution.id == execution_id).first()
        if not execution:
            await websocket.close(code=4004, reason="Not found")
            return
    finally:
        db.close()

    current_conns = _ws_connections.get(execution_id, [])
    if len(current_conns) >= MAX_WS_CONNECTIONS_PER_EXEC:
        logger.warning(f"WS      | Connection cap reached for {execution_id[:8]}...")
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION, reason="Too many connections")
        return

    try:
        after_seq = int(websocket.query_params.get("after_seq", "0") or "0")
    except ValueError:
        after_seq = 0
    after_seq = max(0, after_seq)

    if execution_id not in _ws_connections:
        _ws_connections[execution_id] = []
    _ws_connections[execution_id].append(websocket)
    _ws_seq[id(websocket)] = after_seq

    logger.info(f"WS      | Client connected for execution {execution_id[:8]}...")

    db = SessionLocal()
    try:
        rows = fetch_events(db, execution_id, after_seq=after_seq)
    finally:
        db.close()
    try:
        for row in rows:
            await websocket.send_text(json.dumps(event_to_wire(row)))
            _ws_seq[id(websocket)] = max(_ws_seq.get(id(websocket), after_seq), row.seq)
    except Exception:
        _cleanup_ws(execution_id, websocket)
        return

    try:
        while True:
            data = await websocket.receive_text()
            if data == "ping":
                await websocket.send_text("pong")
    except WebSocketDisconnect:
        logger.info(f"WS      | Client disconnected from {execution_id[:8]}...")
    except Exception:
        pass
    finally:
        _cleanup_ws(execution_id, websocket)


def _cleanup_ws(execution_id: str, websocket: WebSocket) -> None:
    """Unregister one socket and drop its replay watermark."""
    if execution_id in _ws_connections:
        _ws_connections[execution_id] = [ws for ws in _ws_connections[execution_id] if ws != websocket]
    _ws_seq.pop(id(websocket), None)


# ═════════════════════════════════════════════════════════════════════
# Background Execution Runner (desktop/dev, persisted locally)
# ═════════════════════════════════════════════════════════════════════


def _persist_agent_runs(db, execution_id: str, routing: list) -> None:
    """Store one AgentRun row per agent: model/provider names only, never keys."""
    for entry in routing or []:
        db.add(
            AgentRun(
                execution_id=execution_id,
                agent_type=entry.get("agent_type", "unknown"),
                role_description=entry.get("role_description", ""),
                model=entry.get("model", ""),
                provider=entry.get("provider_name", ""),
                status="completed",
            )
        )


async def _run_execution(
    execution_id: str,
    question: str,
    time_budget_minutes: int,
    provider_keys: dict[str, str] | None = None,
    search_keys: dict[str, str] | None = None,
    is_demo: bool = False,
):
    """Run the orchestrator in the background and stream to WS clients."""
    logger.info(f"Exec    │ Starting background execution {execution_id[:8]}...")

    async def on_progress(event: dict):
        state = event.get("state") or (event.get("data") or {}).get("state")
        if state:
            _persist_state(execution_id, state)
        _persist_progress_event(execution_id, event)
        connections = _ws_connections.get(execution_id, [])
        message = json.dumps(event)
        dead = []
        for ws in connections:
            try:
                watermark = _ws_seq.get(id(ws), 0)
                seq = event.get("seq")
                if isinstance(seq, int) and seq <= watermark:
                    continue
                await ws.send_text(message)
                if isinstance(seq, int):
                    _ws_seq[id(ws)] = max(watermark, seq)
            except Exception:
                dead.append(ws)
        for ws in dead:
            if ws in connections:
                connections.remove(ws)
            _ws_seq.pop(id(ws), None)

    try:
        router_override = None
        if is_demo:
            from pathlib import Path

            from src.providers.replay_provider import ReplayRouter

            demo_path = Path("recordings/demo.json")
            if not demo_path.exists():
                import glob
                import os

                recordings = glob.glob("recordings/run-*.json")
                if recordings:
                    demo_path = Path(max(recordings, key=os.path.getctime))

            if demo_path.exists():
                logger.info(f"Exec    │ Loading demo recording from {demo_path}")
                router_override = ReplayRouter.load(demo_path, delay_scale=1.0)
            else:
                logger.warning("Exec    │ Demo mode requested but no recordings found.")

        result = await _orchestrator.execute(
            execution_id=execution_id,
            question=question,
            time_budget_minutes=time_budget_minutes,
            on_progress=on_progress,
            provider_keys=provider_keys,
            search_keys=search_keys,
            router_override=router_override,
        )

        db = SessionLocal()
        try:
            execution = db.query(Execution).filter(Execution.id == execution_id).first()
            if execution:
                execution.status = result.status
                execution.final_answer = result.answer
                execution.final_sources = result.sources
                execution.consensus_score = result.consensus_score
                execution.problem_type = result.problem_type
                execution.complexity = result.complexity
                execution.agent_count = result.agent_count
                execution.debate_rounds = result.debate_rounds
                execution.total_tokens_used = result.total_tokens
                execution.completed_at = datetime.now(timezone.utc)
                _persist_agent_runs(db, execution_id, result.routing)
                db.commit()
        finally:
            db.close()

    except asyncio.CancelledError:
        logger.info(f"Exec    │ Background execution {execution_id[:8]}... cancelled")
        _persist_state(execution_id, "cancelled", finished=True)
    except Exception as e:
        logger.error(f"Exec    │ Background execution failed: {e}")
        db = SessionLocal()
        try:
            execution = db.query(Execution).filter(Execution.id == execution_id).first()
            if execution:
                execution.status = "failed"
                execution.completed_at = datetime.now(timezone.utc)
                db.commit()
        finally:
            db.close()
    finally:
        _ws_connections.pop(execution_id, None)
        _run_tasks.pop(execution_id, None)
        await execution_tracker.release("global")


def _cancel_task(task: asyncio.Task) -> None:
    """Request cancellation of a background task from any thread."""
    try:
        running: asyncio.AbstractEventLoop | None = asyncio.get_running_loop()
    except RuntimeError:
        running = None
    try:
        owner = task.get_loop()
    except RuntimeError:
        owner = None
    if owner is not None and running is not None and owner is not running:
        owner.call_soon_threadsafe(task.cancel)
    else:
        task.cancel()


def _persist_progress_event(execution_id: str, event: dict) -> None:
    """Append one recorder-built event to the execution_events log (desktop)."""
    if settings.is_web:
        return
    if not isinstance(event.get("event_type"), str):
        return
    db = SessionLocal()
    try:
        seq = event.get("seq")
        if not isinstance(seq, int) or seq < 1:
            seq = fetch_latest_seq(db, execution_id) + 1
            event = {**event, "seq": seq}
        persist_event(db, execution_id, event)
    finally:
        db.close()


def _persist_state(execution_id: str, state: str, finished: bool = False) -> None:
    """Write a lifecycle state to the execution row (desktop, best-effort)."""
    if settings.is_web:
        return
    db = SessionLocal()
    try:
        execution = db.query(Execution).filter(Execution.id == execution_id).first()
        if execution is None:
            return
        execution.status = state
        if finished:
            execution.completed_at = datetime.now(timezone.utc)
        db.commit()
    except Exception as e:  # noqa: BLE001 — reporting must not break execution
        logger.warning(f"Exec    │ State persist skipped for {execution_id[:8]}...: {e}")
    finally:
        db.close()
