"""
Assembly — Executions API Routes

Handles question submission, execution tracking, and WebSocket
real-time progress streaming.
"""

import asyncio
import json
from datetime import datetime, timezone

from fastapi import (
    APIRouter,
    Depends,
    HTTPException,
    Query,
    WebSocket,
    WebSocketDisconnect,
    status,
)
from sqlalchemy.orm import Session

from src.core.logging_config import logger
from src.core.security import decode_access_token, get_current_user_id
from src.database.base import SessionLocal, get_db
from src.database.models import AgentRun, Conversation, Execution, Message
from src.database.schemas import (
    ExecutionCancelResponse,
    ExecutionRequest,
    ExecutionResponse,
    PlannerSuggestionResponse,
    PreflightResponse,
)
from src.orchestration.capacity import (
    KeyBudget,
    heuristic_suggestion,
    plan_capacity,
)
from src.orchestration.orchestrator import Orchestrator

router = APIRouter(prefix="/api/executions", tags=["executions"])

# ── Active WebSocket connections per execution ───────────────────────
_ws_connections: dict[str, list[WebSocket]] = {}

# ── Background execution tasks per execution id ──────────────────────
# Lets POST /{id}/cancel interrupt a running execution. Entries are
# removed when the run settles (see _run_execution finally-block).
_run_tasks: dict[str, asyncio.Task] = {}

# ── Shared orchestrator instance ─────────────────────────────────────
_orchestrator = Orchestrator()


@router.post("/", response_model=ExecutionResponse)
async def create_execution(
    req: ExecutionRequest,
    user_id: str = Depends(get_current_user_id),
    db: Session = Depends(get_db),
):
    """
    Submit a question and start an execution.
    
    Creates a conversation (if needed), stores the user message,
    creates the execution record, and kicks off the orchestrator
    in the background.
    """
    # Validate time budget
    if req.time_budget_minutes not in (3, 5, 10, 15):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Time budget must be 3, 5, 10, or 15 minutes.",
        )

    # Create or get conversation
    if req.conversation_id:
        conversation = (
            db.query(Conversation)
            .filter(Conversation.id == req.conversation_id, Conversation.user_id == user_id)
            .first()
        )
        if not conversation:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Conversation not found.",
            )
    else:
        # Create new conversation with question as title
        title = req.question[:80] + ("..." if len(req.question) > 80 else "")
        conversation = Conversation(
            user_id=user_id,
            title=title,
        )
        db.add(conversation)
        db.commit()
        db.refresh(conversation)

    # Save user message
    user_message = Message(
        conversation_id=conversation.id,
        role="user",
        content=req.question,
    )
    db.add(user_message)

    # Create execution record
    execution = Execution(
        conversation_id=conversation.id,
        question=req.question,
        time_budget_minutes=req.time_budget_minutes,
        status="pending",
        started_at=datetime.now(timezone.utc),
    )
    db.add(execution)
    db.commit()
    db.refresh(execution)

    # Launch orchestrator in background. provider_keys (if any) travel only
    # in memory for this run and are wiped by the orchestrator afterwards —
    # they are never stored on the execution record below.
    _run_tasks[execution.id] = asyncio.get_event_loop().create_task(
        _run_execution(
            execution.id,
            req.question,
            req.time_budget_minutes,
            conversation.id,
            req.provider_keys,
        )
    )

    return ExecutionResponse.model_validate(execution)


@router.post("/{execution_id}/cancel", response_model=ExecutionCancelResponse)
async def cancel_execution(
    execution_id: str,
    user_id: str = Depends(get_current_user_id),
    db: Session = Depends(get_db),
):
    """Request cancellation of a running execution.

    Flags the run in the orchestrator (checked at phase boundaries) and
    cancels its background task so in-flight provider calls abort
    promptly; quota leases release via their context managers. The run
    settles to status "cancelled". Idempotent: already-terminal runs
    report their current status.
    """
    execution = db.query(Execution).filter(Execution.id == execution_id).first()
    if not execution:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Execution not found.",
        )

    # Verify ownership
    conversation = db.query(Conversation).filter(
        Conversation.id == execution.conversation_id,
        Conversation.user_id == user_id,
    ).first()
    if not conversation:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied.")

    if execution.status in ("completed", "failed", "failed_partial", "cancelled"):
        return ExecutionCancelResponse(id=execution_id, status=execution.status)

    # Flag first (phase-boundary checks), then interrupt the task itself
    # so a run stuck inside a long provider call aborts without waiting.
    _orchestrator.request_cancel(execution_id)
    task = _run_tasks.get(execution_id)
    if task is not None and not task.done():
        _cancel_task(task)
        logger.info(f"Exec    │ Cancel delivered to {execution_id[:8]}...")

    return ExecutionCancelResponse(id=execution_id, status="cancelling")


@router.get("/preflight", response_model=PreflightResponse)
async def preflight(
    question: str = Query(..., min_length=1, max_length=10000),
    time_budget_minutes: int = Query(5, ge=3, le=15),
    user_id: str = Depends(get_current_user_id),
):
    """Capacity verdict for a question + tier WITHOUT running an execution.

    Uses a cheap heuristic suggestion (no LLM call, no quota spent) plus
    live per-key quota counts. Keys never appear here: only counts and
    provider/family names (BYOK rule). NOTE: this route must stay above
    the `/{execution_id}` route so "preflight" is not read as an ID.
    """
    if time_budget_minutes not in (3, 5, 10, 15):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Time budget must be 3, 5, 10, or 15 minutes.",
        )

    suggestion = heuristic_suggestion(question)
    router = _orchestrator.router
    snapshot = router.quota_snapshot()
    keys = [
        KeyBudget(
            provider=entry.get("provider", "unknown"),
            rpm_limit=entry.get("rpm_limit"),
            rpd_remaining=entry.get("rpd_remaining"),
        )
        for entry in snapshot
    ]
    plan = plan_capacity(keys, time_budget_minutes, suggestion)
    warnings = list(plan.warnings)
    for entry in snapshot:
        if (entry.get("cooldown_seconds") or 0) > 0:
            warnings.append(
                f"Provider {entry.get('provider')} is cooling down "
                f"({entry.get('cooldown_seconds')}s); "
                "it may be unavailable at execution start."
            )
            break

    return PreflightResponse(
        question=question,
        requested_tier=time_budget_minutes,
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
        families=router.available_families(),
    )


@router.get("/{execution_id}", response_model=ExecutionResponse)
async def get_execution(
    execution_id: str,
    user_id: str = Depends(get_current_user_id),
    db: Session = Depends(get_db),
):
    """Get execution status and result."""
    execution = db.query(Execution).filter(Execution.id == execution_id).first()
    if not execution:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Execution not found.",
        )

    # Verify ownership
    conversation = db.query(Conversation).filter(
        Conversation.id == execution.conversation_id,
        Conversation.user_id == user_id,
    ).first()
    if not conversation:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied.")

    return ExecutionResponse.model_validate(execution)


# ═════════════════════════════════════════════════════════════════════
# WebSocket — Real-time Progress
# ═════════════════════════════════════════════════════════════════════

@router.websocket("/ws/{execution_id}")
async def websocket_progress(websocket: WebSocket, execution_id: str):
    """
    WebSocket endpoint for real-time execution progress.
    
    The frontend connects here after submitting a question
    to receive live updates: agent status, consensus score,
    timer, and the final answer.
    """
    await websocket.accept()

    # Authenticate via token query param
    token = websocket.query_params.get("token", "")
    try:
        if token:
            decode_access_token(token)
    except Exception:
        await websocket.close(code=4001, reason="Authentication failed")
        return

    # Register connection
    if execution_id not in _ws_connections:
        _ws_connections[execution_id] = []
    _ws_connections[execution_id].append(websocket)

    logger.info(f"WS      │ Client connected for execution {execution_id[:8]}...")

    try:
        # Keep the connection alive
        while True:
            # Wait for client messages (ping/pong or close)
            data = await websocket.receive_text()
            if data == "ping":
                await websocket.send_text("pong")
    except WebSocketDisconnect:
        logger.info(f"WS      │ Client disconnected from {execution_id[:8]}...")
    except Exception:
        pass
    finally:
        if execution_id in _ws_connections:
            _ws_connections[execution_id] = [
                ws for ws in _ws_connections[execution_id] if ws != websocket
            ]


# ═════════════════════════════════════════════════════════════════════
# Background Execution Runner
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
    conversation_id: str,
    provider_keys: dict[str, str] | None = None,
):
    """
    Run the orchestrator in the background and stream progress
    to connected WebSocket clients.
    """
    logger.info(f"Exec    │ Starting background execution {execution_id[:8]}...")

    async def on_progress(event: dict):
        """Broadcast progress events to all connected WebSocket clients."""
        # Persist lifecycle state so GET /{id} (and cancel polling) sees
        # live phases, not just the terminal write at the end.
        state = (event.get("data") or {}).get("state")
        if event.get("event_type") == "status_update" and state:
            _persist_state(execution_id, state)
        connections = _ws_connections.get(execution_id, [])
        message = json.dumps(event)
        dead = []
        for ws in connections:
            try:
                await ws.send_text(message)
            except Exception:
                dead.append(ws)
        # Remove dead connections
        for ws in dead:
            if ws in connections:
                connections.remove(ws)

    try:
        result = await _orchestrator.execute(
            execution_id=execution_id,
            question=question,
            time_budget_minutes=time_budget_minutes,
            on_progress=on_progress,
            provider_keys=provider_keys,
        )

        # Update database with results
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

                # Cancelled runs produce no answer: persist the terminal
                # state but no assistant message.
                if result.status != "cancelled":
                    # Save assistant message to conversation
                    assistant_message = Message(
                        conversation_id=conversation_id,
                        role="assistant",
                        content=result.answer,
                        sources=result.sources,
                        execution_id=execution_id,
                    )
                    db.add(assistant_message)

                # Update conversation timestamp
                conv = db.query(Conversation).filter(Conversation.id == conversation_id).first()
                if conv:
                    conv.updated_at = datetime.now(timezone.utc)

                _persist_agent_runs(db, execution_id, result.routing)

                db.commit()
        finally:
            db.close()

    except asyncio.CancelledError:
        # Cancellation landed outside execute() (or execute() re-raised):
        # mark CANCELLED without an answer. Quota leases unwind via
        # their own context managers; keys were wiped by the orchestrator.
        logger.info(f"Exec    │ Background execution {execution_id[:8]}... cancelled")
        _persist_state(execution_id, "cancelled", finished=True)
    except Exception as e:
        logger.error(f"Exec    │ Background execution failed: {e}")
        # Update status to failed
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
        # Cleanup WebSocket connections + task registry
        _ws_connections.pop(execution_id, None)
        _run_tasks.pop(execution_id, None)


def _cancel_task(task: asyncio.Task) -> None:
    """Request cancellation of a background task from any thread.

    The endpoint usually shares the task's loop (uvicorn), but callers on
    another thread/loop (e.g. tests driving a foreign task) must route
    through call_soon_threadsafe — direct cancel() would raise there.
    """
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


def _persist_state(execution_id: str, state: str, finished: bool = False) -> None:
    """Write a lifecycle state to the execution row (best-effort).

    Intermediate states make live progress visible to GET /{id}; terminal
    states set completed_at. Never raises: persistence must not break the
    run it reports on.
    """
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
        logger.warning(
            f"Exec    │ State persist skipped for {execution_id[:8]}...: {e}"
        )
    finally:
        db.close()
