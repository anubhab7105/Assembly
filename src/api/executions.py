"""
Assembly — Executions API Routes

Handles question submission, execution tracking, and WebSocket
real-time progress streaming.
"""

import asyncio
import json
from datetime import datetime, timezone
from typing import Dict
from fastapi import APIRouter, Depends, HTTPException, WebSocket, WebSocketDisconnect, status
from sqlalchemy.orm import Session

from src.database.base import get_db, SessionLocal
from src.database.models import Execution, Conversation, Message
from src.database.schemas import ExecutionRequest, ExecutionResponse
from src.orchestration.orchestrator import Orchestrator
from src.core.security import get_current_user_id, decode_access_token
from src.core.logging_config import logger

router = APIRouter(prefix="/api/executions", tags=["executions"])

# ── Active WebSocket connections per execution ───────────────────────
_ws_connections: Dict[str, list[WebSocket]] = {}

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

    # Launch orchestrator in background
    asyncio.get_event_loop().create_task(
        _run_execution(execution.id, req.question, req.time_budget_minutes, conversation.id)
    )

    return ExecutionResponse.model_validate(execution)


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

async def _run_execution(
    execution_id: str,
    question: str,
    time_budget_minutes: int,
    conversation_id: str,
):
    """
    Run the orchestrator in the background and stream progress
    to connected WebSocket clients.
    """
    logger.info(f"Exec    │ Starting background execution {execution_id[:8]}...")

    async def on_progress(event: dict):
        """Broadcast progress events to all connected WebSocket clients."""
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

                db.commit()
        finally:
            db.close()

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
        # Cleanup WebSocket connections
        _ws_connections.pop(execution_id, None)
