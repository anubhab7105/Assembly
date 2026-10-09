"""
Assembly — Progress event contracts (docs/WORKFLOW.md section 8).

Single home for the backend→UI event system:

- ``ProgressEventType``: the 17 canonical dotted names (§8 table plus
  ``execution.cancelled`` for the §2 CANCELLED state, which §8 omits).
- One strict Pydantic payload model per type (``extra="forbid"``).
  Payloads carry short human-readable summaries only — never keys,
  never full chain-of-thought (see ``sanitize_payload``).
- ``ProgressEvent``: the wire/DB envelope
  ``{event_type, execution_id, seq, data, timestamp}``.
- ``EventRecorder``: validates + sanitizes + assigns dense per-execution
  sequence numbers. Used by the orchestrator at emission time.
- ``persist_event`` / ``fetch_events`` / ``fetch_latest_seq``: DB layer
  used by the API for the event log, WS replay and the REST fallback.
- ``event_schema_bundle()``: machine-readable schema for the export
  script (``scripts/export_event_schema.py``) so the frontend can derive
  TypeScript types.

Import direction: orchestrator and api.executions import from here;
this module imports only pydantic, the DB layer and logging — never
orchestrator code, so there are no cycles.
"""

from datetime import datetime, timezone
from enum import Enum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, SecretStr
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from src.core.logging_config import logger
from src.database.models import ExecutionEvent


class ProgressEventType(str, Enum):
    """Canonical event names (WORKFLOW §8 + execution.cancelled)."""

    EXECUTION_STARTED = "execution.started"
    PLAN_READY = "plan.ready"
    TEAM_READY = "team.ready"
    AGENT_STATUS = "agent.status"
    ROUND_STARTED = "round.started"
    ROUND_FINISHED = "round.finished"
    DISAGREEMENT_OPENED = "disagreement.opened"
    DISAGREEMENT_RESOLVED = "disagreement.resolved"
    SOURCE_FOUND = "source.found"
    SOURCE_VERIFIED = "source.verified"
    CONSENSUS_UPDATED = "consensus.updated"
    QUOTA_WARNING = "quota.warning"
    TIMER_TICK = "timer.tick"
    SYNTHESIS_STARTED = "synthesis.started"
    EXECUTION_COMPLETED = "execution.completed"
    EXECUTION_FAILED_PARTIAL = "execution.failed_partial"
    EXECUTION_CANCELLED = "execution.cancelled"


# ═════════════════════════════════════════════════════════════════════
# Payload models — short human-readable summaries, never secrets/CoT
# ═════════════════════════════════════════════════════════════════════


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


class ExecutionStartedPayload(_Strict):
    tier_minutes: int = Field(ge=1)
    deadline_seconds: float = Field(ge=0)


class PlanReadyPayload(_Strict):
    problem_type: str = Field(min_length=1)
    complexity: str = Field(min_length=1)
    agent_count: int = Field(ge=0)


class TeamRole(_Strict):
    agent_id: str = Field(min_length=1)
    agent_type: str = Field(min_length=1)
    model: str = ""
    provider_name: str = ""
    role_description: str = ""
    family: str = ""


class TeamReadyPayload(_Strict):
    roles: list[TeamRole] = Field(default_factory=list)


class AgentStatusPayload(_Strict):
    role: str = ""
    activity: str = Field(min_length=1, max_length=500)
    state: str = Field(min_length=1)


class RoundStartedPayload(_Strict):
    round: int = Field(ge=1)
    goal: str = Field(min_length=1, max_length=500)


class RoundFinishedPayload(_Strict):
    round: int = Field(ge=1)
    outcome: str = Field(min_length=1, max_length=500)


class DisagreementOpenedPayload(_Strict):
    description: str = Field(min_length=1, max_length=500)
    agents: list[str] = Field(default_factory=list)
    round: int = Field(ge=1)


class DisagreementResolvedPayload(_Strict):
    description: str = Field(min_length=1, max_length=500)
    agents: list[str] = Field(default_factory=list)
    round: int = Field(ge=1)


class SourcePayload(_Strict):
    # §8 lists title + domain; snippet rides along because researchers
    # attach it and the final answer renders it.
    title: str = ""
    domain: str = ""
    url: str = ""
    snippet: str = ""


class ConsensusUpdatedPayload(_Strict):
    score: float = Field(ge=0.0, le=1.0)
    new_info_rate: float = Field(ge=0.0, le=1.0)
    decision: str = Field(min_length=1)
    reason: str = Field(min_length=1, max_length=1000)
    round: int = Field(ge=1)


class QuotaWarningPayload(_Strict):
    provider: str = Field(min_length=1)
    remaining: float = Field(ge=0.0)
    detail: str = Field(default="", max_length=500)


class TimerTickPayload(_Strict):
    seconds_remaining: float = Field(ge=0.0)


class SynthesisStartedPayload(_Strict):
    """No payload per §8 (\"none\"); the event itself is the signal."""


class ExecutionCompletedPayload(_Strict):
    status: str = Field(default="completed", pattern="^(completed|failed)$")
    answer: str = ""
    sources: list[SourcePayload] = Field(default_factory=list)
    confidence_label: str = Field(default="low", pattern="^(high|medium|low)$")
    consensus_score: float = Field(default=0.0, ge=0.0, le=1.0)
    agent_count: int = Field(default=0, ge=0)
    providers_used: list[str] = Field(default_factory=list)
    tokens_used: int = Field(default=0, ge=0)
    debate_rounds: int = Field(default=0, ge=0)
    elapsed_seconds: float = Field(default=0.0, ge=0.0)
    verification: dict = Field(default_factory=dict)


class ExecutionFailedPartialPayload(_Strict):
    status: str = Field(default="failed", pattern="^(failed|failed_partial)$")
    reason: str = Field(min_length=1, max_length=1000)
    answer: str = ""


class ExecutionCancelledPayload(_Strict):
    status: str = Field(default="cancelled", pattern="^cancelled$")
    reason: str = Field(min_length=1, max_length=500)


PAYLOAD_MODELS: dict[ProgressEventType, type[BaseModel]] = {
    ProgressEventType.EXECUTION_STARTED: ExecutionStartedPayload,
    ProgressEventType.PLAN_READY: PlanReadyPayload,
    ProgressEventType.TEAM_READY: TeamReadyPayload,
    ProgressEventType.AGENT_STATUS: AgentStatusPayload,
    ProgressEventType.ROUND_STARTED: RoundStartedPayload,
    ProgressEventType.ROUND_FINISHED: RoundFinishedPayload,
    ProgressEventType.DISAGREEMENT_OPENED: DisagreementOpenedPayload,
    ProgressEventType.DISAGREEMENT_RESOLVED: DisagreementResolvedPayload,
    ProgressEventType.SOURCE_FOUND: SourcePayload,
    ProgressEventType.SOURCE_VERIFIED: SourcePayload,
    ProgressEventType.CONSENSUS_UPDATED: ConsensusUpdatedPayload,
    ProgressEventType.QUOTA_WARNING: QuotaWarningPayload,
    ProgressEventType.TIMER_TICK: TimerTickPayload,
    ProgressEventType.SYNTHESIS_STARTED: SynthesisStartedPayload,
    ProgressEventType.EXECUTION_COMPLETED: ExecutionCompletedPayload,
    ProgressEventType.EXECUTION_FAILED_PARTIAL: ExecutionFailedPartialPayload,
    ProgressEventType.EXECUTION_CANCELLED: ExecutionCancelledPayload,
}


class ProgressEvent(BaseModel):
    """Wire + REST envelope for one sequenced progress event.

    ``state`` is envelope metadata (the §2 lifecycle state at emission),
    not §8 payload content: the API persists it to Execution.status so
    live phases stay visible to GET /{id} and cancel polling.
    """

    model_config = ConfigDict(extra="forbid")

    event_type: ProgressEventType
    execution_id: str = Field(min_length=1)
    seq: int = Field(ge=1)
    state: str | None = None
    data: dict[str, Any] = Field(default_factory=dict)
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


# ═════════════════════════════════════════════════════════════════════
# Sanitization — events must never contain keys or full CoT
# ═════════════════════════════════════════════════════════════════════

#: Exact payload keys that are never allowed (case-insensitive).
_FORBIDDEN_KEYS = frozenset(
    {
        "provider_keys",
        "api_key",
        "apikey",
        "authorization",
        "secret",
        "password",
        "passwd",
        "pwd",
        "access_token",
        "refresh_token",
        "id_token",
        "client_secret",
        "private_key",
        "seed_phrase",
        "mnemonic",
        "key",
    }
)

#: Key suffixes that mark a secret (checked after the exact set, so
#: benign counters like "tokens_used" survive).
_FORBIDDEN_SUFFIXES = ("_secret", "_token", "_key", "_password")

#: Backstop length for any single string value (builders already keep
#: descriptions ≈200 chars; this only catches programmer error).
MAX_STRING_CHARS = 2000

_SECRET_REPLACEMENT = "***"


def _is_forbidden_key(name: str) -> bool:
    lowered = name.lower()
    if lowered in _FORBIDDEN_KEYS:
        return True
    return lowered.endswith(_FORBIDDEN_SUFFIXES)


def sanitize_payload(value: Any) -> Any:
    """Recursively strip secrets and truncate long strings.

    - Drops forbidden keys at any depth (dicts only; lists are kept).
    - Replaces SecretStr values with "***" (they are not JSON-serializable
      and must never reach the wire).
    - Truncates strings longer than MAX_STRING_CHARS.
    - Converts datetimes to ISO strings; unknown objects become truncated
      reprs so json.dumps can never fail on an event payload.
    """
    if isinstance(value, SecretStr):
        return _SECRET_REPLACEMENT
    if isinstance(value, dict):
        return {
            key: sanitize_payload(item)
            for key, item in value.items()
            if not (isinstance(key, str) and _is_forbidden_key(key))
        }
    if isinstance(value, (list, tuple)):
        return [sanitize_payload(item) for item in value]
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, str):
        if len(value) > MAX_STRING_CHARS:
            return value[:MAX_STRING_CHARS] + "…[truncated]"
        return value
    if value is None or isinstance(value, (bool, int, float)):
        return value
    if isinstance(value, BaseModel):
        return sanitize_payload(value.model_dump())
    text = repr(value)
    if len(text) > MAX_STRING_CHARS:
        text = text[:MAX_STRING_CHARS] + "…[truncated]"
    return text


# ═════════════════════════════════════════════════════════════════════
# Recorder — validate + sanitize + sequence at emission time
# ═════════════════════════════════════════════════════════════════════


class EventRecorder:
    """Per-execution event source: strict validation, dense seq numbers.

    The orchestrator builds every progress event through here, so a
    malformed payload is a loud, test-visible bug — never silent wire
    corruption. ``emit`` returns the wire dict
    ``{event_type, execution_id, seq, data, timestamp}``.
    """

    def __init__(self, execution_id: str) -> None:
        self.execution_id = execution_id
        self._seq = 0
        self._events: list[dict[str, Any]] = []

    @property
    def latest_seq(self) -> int:
        """Highest sequence number assigned so far (0 when empty)."""
        return self._seq

    def emit(
        self,
        event_type: ProgressEventType | str,
        payload: BaseModel | dict[str, Any],
        timestamp: datetime | None = None,
        state: str | None = None,
    ) -> dict[str, Any]:
        """Validate, sanitize, sequence and store one event.

        Raises pydantic.ValidationError on contract violations — callers
        must not let that kill a run (see orchestrator._emit_event).
        """
        resolved = ProgressEventType(event_type)
        model = PAYLOAD_MODELS[resolved]
        if isinstance(payload, BaseModel):
            data = sanitize_payload(payload.model_dump())
        else:
            data = sanitize_payload(model.model_validate(payload).model_dump())
        self._seq += 1
        wire = {
            "event_type": resolved.value,
            "execution_id": self.execution_id,
            "seq": self._seq,
            "state": state,
            "data": data,
            "timestamp": (timestamp or datetime.now(timezone.utc)).isoformat(),
        }
        self._events.append(wire)
        return wire

    def events_after(
        self, after_seq: int = 0, limit: int = 2000
    ) -> list[dict[str, Any]]:
        """In-memory replay slice (mirrors the DB/REST ordering contract)."""
        return [event for event in self._events if event["seq"] > after_seq][
            : max(0, limit)
        ]


# ═════════════════════════════════════════════════════════════════════
# Helpers shared by emission sites
# ═════════════════════════════════════════════════════════════════════


def confidence_label(consensus_score: float) -> str:
    """Wording bands per WORKFLOW §6: high ≥ 0.85, medium ≥ 0.60."""
    if consensus_score >= 0.85:
        return "high"
    if consensus_score >= 0.60:
        return "medium"
    return "low"


def diff_disagreements(
    previous: dict[tuple[str, tuple[str, ...]], str],
    open_disagreements: list[dict[str, Any]],
    round_number: int,
) -> tuple[list[tuple[ProgressEventType, dict[str, Any]]], dict]:
    """Diff consensus open-disagreements into opened/resolved events.

    Pure function (no I/O) so the diffing rule is unit-testable. Keys are
    (agent_id, sorted targets); descriptions quote positions truncated to
    200 chars — never full chain-of-thought.
    """
    current: dict[tuple[str, tuple[str, ...]], str] = {}
    for item in open_disagreements:
        agent_id = str(item.get("agent_id", "?"))
        targets = tuple(sorted(str(t) for t in item.get("disagrees_with", [])))
        position = str(item.get("position", ""))[:200]
        description = (
            f"{agent_id} disputes {', '.join(targets) or 'the consensus'}: "
            f"{position or 'no details'}"
        )
        current[(agent_id, targets)] = description

    emitted: list[tuple[ProgressEventType, dict[str, Any]]] = []
    for key, description in current.items():
        if key not in previous:
            agent_id, targets = key
            emitted.append(
                (
                    ProgressEventType.DISAGREEMENT_OPENED,
                    {
                        "description": description,
                        "agents": [agent_id, *targets],
                        "round": round_number,
                    },
                )
            )
    for key, description in previous.items():
        if key not in current:
            agent_id, targets = key
            emitted.append(
                (
                    ProgressEventType.DISAGREEMENT_RESOLVED,
                    {
                        "description": f"Resolved: {description}",
                        "agents": [agent_id, *targets],
                        "round": round_number,
                    },
                )
            )
    return emitted, current


# ═════════════════════════════════════════════════════════════════════
# Persistence — DB rows backing WS replay + REST fallback
# ═════════════════════════════════════════════════════════════════════


def persist_event(db: Session, execution_id: str, event: dict[str, Any]) -> bool:
    """Append one recorder-built event row. Best-effort: never raises.

    Web mode is stateless: no-op returning False (in-memory replay only).
    Returns True when stored. Duplicate (execution_id, seq) rows are
    ignored so re-delivery can never corrupt the log order.
    """
    try:
        from src.core.config import settings

        if settings.is_web:
            return False
    except Exception:  # noqa: BLE001 — settings trouble means no-op
        return False
    try:
        timestamp = datetime.now(timezone.utc)
        raw_timestamp = event.get("timestamp")
        if isinstance(raw_timestamp, str) and raw_timestamp:
            try:
                timestamp = datetime.fromisoformat(raw_timestamp)
            except ValueError:
                pass
        db.add(
            ExecutionEvent(
                execution_id=execution_id,
                seq=int(event["seq"]),
                type=str(event["event_type"]),
                payload=dict(event.get("data") or {}),
                created_at=timestamp,
            )
        )
        db.commit()
        return True
    except IntegrityError:
        db.rollback()  # duplicate seq: already stored, order preserved
        return False
    except Exception as e:  # noqa: BLE001 — reporting must not break execution
        db.rollback()
        logger.warning(f"Events  │ persist skipped for {execution_id[:8]}...: {e}")
        return False


def fetch_events(
    db: Session, execution_id: str, after_seq: int = 0, limit: int = 2000
) -> list[ExecutionEvent]:
    """Replay slice in seq order (the ordering contract)."""
    return (
        db.query(ExecutionEvent)
        .filter(
            ExecutionEvent.execution_id == execution_id,
            ExecutionEvent.seq > after_seq,
        )
        .order_by(ExecutionEvent.seq.asc())
        .limit(max(1, min(limit, 2000)))
        .all()
    )


def fetch_latest_seq(db: Session, execution_id: str) -> int:
    """Highest persisted seq for an execution (0 when the log is empty)."""
    from sqlalchemy import func

    value = (
        db.query(func.max(ExecutionEvent.seq))
        .filter(ExecutionEvent.execution_id == execution_id)
        .scalar()
    )
    return int(value or 0)


def event_to_wire(row: ExecutionEvent) -> dict[str, Any]:
    """Rebuild the broadcast wire shape from a persisted row."""
    created = row.created_at
    if isinstance(created, datetime):
        timestamp = created.isoformat()
    else:
        timestamp = datetime.now(timezone.utc).isoformat()
    return {
        "event_type": row.type,
        "execution_id": row.execution_id,
        "seq": row.seq,
        "data": dict(row.payload or {}),
        "timestamp": timestamp,
    }


# ═════════════════════════════════════════════════════════════════════
# Schema bundle — machine-readable contract for frontend typegen
# ═════════════════════════════════════════════════════════════════════


def event_schema_bundle() -> dict[str, Any]:
    """Full event contract: envelope + every payload model as JSON Schema."""
    return {
        "version": 1,
        "event_types": [event_type.value for event_type in ProgressEventType],
        "envelope": ProgressEvent.model_json_schema(),
        "payloads": {
            event_type.value: PAYLOAD_MODELS[event_type].model_json_schema()
            for event_type in ProgressEventType
        },
    }
