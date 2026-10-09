"""
Assembly — Pydantic Schemas

Request / response schemas for all API endpoints.
"""

from datetime import datetime

from pydantic import BaseModel, Field

from src.api.events import ProgressEvent


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
    sources: list | None = None
    execution_id: str | None = None
    created_at: datetime

    class Config:
        from_attributes = True


class ConversationResponse(BaseModel):
    id: str
    title: str
    created_at: datetime
    updated_at: datetime | None = None
    messages: list[MessageResponse] = []

    class Config:
        from_attributes = True


class ConversationListItem(BaseModel):
    id: str
    title: str
    created_at: datetime
    updated_at: datetime | None = None
    message_count: int = 0

    class Config:
        from_attributes = True


# ═════════════════════════════════════════════════════════════════════
# EXECUTIONS
# ═════════════════════════════════════════════════════════════════════
class ExecutionRequest(BaseModel):
    question: str = Field(..., min_length=1, max_length=2000)
    time_budget_minutes: int = Field(..., ge=3, le=15)
    conversation_id: str | None = None  # Attach to existing, or create new
    # Web-mode BYOK keys (provider → key). In-memory for this run only:
    # never written to the database, never logged, never returned.
    provider_keys: dict[str, str] | None = None
    is_demo: bool = False


class ExecutionResponse(BaseModel):
    id: str
    conversation_id: str
    question: str
    time_budget_minutes: int
    status: str
    problem_type: str | None = None
    complexity: str | None = None
    final_answer: str | None = None
    final_sources: list | None = None
    consensus_score: float | None = None
    total_tokens_used: int = 0
    agent_count: int = 0
    debate_rounds: int = 0
    started_at: datetime | None = None
    completed_at: datetime | None = None
    created_at: datetime

    class Config:
        from_attributes = True


class AgentRunResponse(BaseModel):
    id: str
    agent_type: str
    role_description: str | None = None
    model: str
    provider: str
    status: str
    confidence: float | None = None

    class Config:
        from_attributes = True


class ExecutionCancelResponse(BaseModel):
    """Reply to POST /api/executions/{id}/cancel."""

    id: str
    status: str  # "cancelling" while the run winds down, else current state


class PlannerSuggestionResponse(BaseModel):
    roles: list[str] = []
    complexity: str = "medium"
    needs_research: bool = False
    estimated_rounds: int = 1


class PreflightResponse(BaseModel):
    """Capacity verdict for a question + tier, without running anything."""

    question: str
    requested_tier: int
    feasible_tier: int
    feasible: bool
    downgraded: bool
    agents: int
    rounds: int
    search_budget: int
    estimated_calls: int
    estimated_seconds: float
    affordable_calls: int | None = None
    synth_reserve_seconds: float
    warnings: list[str] = []
    explanation: str = ""
    planner_suggestion: PlannerSuggestionResponse = PlannerSuggestionResponse()
    usable_keys: int = 0
    providers: list[str] = []
    families: list[str] = []
    # Tier ceilings + median vs worst case (task 3): rounds are a ceiling,
    # consensus stops early. median = planned rounds (typical early-stop);
    # worst = ceiling rounds (consensus never reached, all rounds run).
    ceiling_agents: int = 0
    ceiling_rounds: int = 0
    expected_calls_median: int = 0
    expected_calls_worst: int = 0
    # Token estimates at measured per-stage rates (avg for median, p90 for
    # worst, including one adversarial strike in worst case).
    expected_tokens_median: int = 0
    expected_tokens_worst: int = 0


# ═════════════════════════════════════════════════════════════════════
# WEBSOCKET PROGRESS EVENTS (docs/WORKFLOW.md section 8)
# ═════════════════════════════════════════════════════════════════════
class EventListResponse(BaseModel):
    """Replayable slice of an execution's event log."""

    events: list[ProgressEvent] = []
    latest_seq: int = 0
