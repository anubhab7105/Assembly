"""Assembly — Pydantic Schemas (stateless web + desktop local)."""

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from src.api.events import ProgressEvent


# ═════════════════════════════════════════════════════════════════════
# STATELESS RUN (web: POST /api/run, SSE)
# ═════════════════════════════════════════════════════════════════════
class UsageSnapshotEntry(BaseModel):
    model_config = ConfigDict(extra="forbid")

    provider: str = Field(min_length=1)
    model: str = Field(default="")
    count: int = Field(default=0, ge=0)
    tokens: int = Field(default=0, ge=0)


class ModelSelection(BaseModel):
    """Frontend model picker output. Empty selected = Auto."""

    model_config = ConfigDict(extra="forbid")

    selected: list[str] = Field(default_factory=list, max_length=50)
    pins: dict[str, str] = Field(default_factory=dict)


class RunRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    question: str = Field(..., min_length=1, max_length=2000)
    time_budget_minutes: int = Field(..., ge=3, le=15)
    # Web-mode BYOK keys (provider → key). In-memory for this run only:
    # never written to disk or database, never logged, never returned.
    provider_keys: dict[str, str] = Field(default_factory=dict, max_length=20)
    model_selection: ModelSelection = Field(default_factory=ModelSelection)
    usage_snapshot: list[UsageSnapshotEntry] = Field(default_factory=list, max_length=200)


class UsageCounters(BaseModel):
    model_config = ConfigDict(extra="forbid")

    provider: str = ""
    model: str = ""
    count: int = 0
    tokens: int = 0


class RunResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    run_id: str
    status: str
    answer: str = ""
    sources: list = Field(default_factory=list)
    consensus_score: float | None = None
    agent_count: int = 0
    debate_rounds: int = 0
    total_tokens_used: int = 0
    usage: list[UsageCounters] = Field(default_factory=list)


# ═════════════════════════════════════════════════════════════════════
# EXECUTIONS (desktop local history)
# ═════════════════════════════════════════════════════════════════════
class ExecutionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    question: str = Field(..., min_length=1, max_length=2000)
    time_budget_minutes: int = Field(..., ge=3, le=15)
    provider_keys: dict[str, str] | None = None
    model_selection: ModelSelection = Field(default_factory=ModelSelection)
    usage_snapshot: list[UsageSnapshotEntry] = Field(default_factory=list)
    is_demo: bool = False


class ExecutionResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
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


class AgentRunResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    agent_type: str
    role_description: str | None = None
    model: str
    provider: str
    status: str
    confidence: float | None = None


class ExecutionCancelResponse(BaseModel):
    """Reply to POST /api/executions/{id}/cancel."""

    id: str
    status: str


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
