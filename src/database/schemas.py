"""
Assembly — Pydantic Schemas

Request / response schemas for all API endpoints.
"""

from datetime import datetime
from typing import Optional, List
from pydantic import BaseModel, EmailStr, Field


# ═════════════════════════════════════════════════════════════════════
# AUTH
# ═════════════════════════════════════════════════════════════════════
class SignupRequest(BaseModel):
    email: str = Field(..., min_length=5)
    password: str = Field(..., min_length=6)
    name: str = Field(..., min_length=1)


class LoginRequest(BaseModel):
    email: str
    password: str


class AuthResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: "UserResponse"


class UserResponse(BaseModel):
    id: str
    email: str
    name: str
    created_at: datetime

    class Config:
        from_attributes = True


# ═════════════════════════════════════════════════════════════════════
# CONVERSATIONS
# ═════════════════════════════════════════════════════════════════════
class MessageResponse(BaseModel):
    id: str
    role: str
    content: str
    sources: Optional[list] = None
    execution_id: Optional[str] = None
    created_at: datetime

    class Config:
        from_attributes = True


class ConversationResponse(BaseModel):
    id: str
    title: str
    created_at: datetime
    updated_at: Optional[datetime] = None
    messages: List[MessageResponse] = []

    class Config:
        from_attributes = True


class ConversationListItem(BaseModel):
    id: str
    title: str
    created_at: datetime
    updated_at: Optional[datetime] = None
    message_count: int = 0

    class Config:
        from_attributes = True


# ═════════════════════════════════════════════════════════════════════
# EXECUTIONS
# ═════════════════════════════════════════════════════════════════════
class ExecutionRequest(BaseModel):
    question: str = Field(..., min_length=1, max_length=10000)
    time_budget_minutes: int = Field(..., ge=3, le=15)
    conversation_id: Optional[str] = None  # Attach to existing, or create new


class ExecutionResponse(BaseModel):
    id: str
    conversation_id: str
    question: str
    time_budget_minutes: int
    status: str
    problem_type: Optional[str] = None
    complexity: Optional[str] = None
    final_answer: Optional[str] = None
    final_sources: Optional[list] = None
    consensus_score: Optional[float] = None
    total_tokens_used: int = 0
    agent_count: int = 0
    debate_rounds: int = 0
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    created_at: datetime

    class Config:
        from_attributes = True


class AgentRunResponse(BaseModel):
    id: str
    agent_type: str
    role_description: Optional[str] = None
    model: str
    provider: str
    status: str
    confidence: Optional[float] = None

    class Config:
        from_attributes = True


# ═════════════════════════════════════════════════════════════════════
# WEBSOCKET PROGRESS EVENTS
# ═════════════════════════════════════════════════════════════════════
class ProgressEvent(BaseModel):
    """Real-time progress event sent via WebSocket."""
    event_type: str  # status_update | agent_update | consensus_update | timer_update | answer_ready | error
    execution_id: str
    data: dict = {}
