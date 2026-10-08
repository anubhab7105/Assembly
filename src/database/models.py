"""
Assembly — Database Models

All ORM models per the PRD database design (Section 20).
"""

import uuid
from datetime import datetime, timezone

from sqlalchemy import (
    JSON,
    Boolean,
    Column,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import relationship

from src.database.base import Base


def generate_uuid() -> str:
    return str(uuid.uuid4())


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


# ═════════════════════════════════════════════════════════════════════
# USER
# ═════════════════════════════════════════════════════════════════════
class User(Base):
    __tablename__ = "users"

    id = Column(String, primary_key=True, default=generate_uuid)
    email = Column(String, unique=True, nullable=False, index=True)
    name = Column(String, nullable=False)
    hashed_password = Column(String, nullable=False)
    created_at = Column(DateTime, default=utc_now)
    updated_at = Column(DateTime, default=utc_now, onupdate=utc_now)

    # Relationships
    conversations = relationship(
        "Conversation", back_populates="user", cascade="all, delete-orphan"
    )


# ═════════════════════════════════════════════════════════════════════
# CONVERSATION & MESSAGES
# ═════════════════════════════════════════════════════════════════════
class Conversation(Base):
    __tablename__ = "conversations"

    id = Column(String, primary_key=True, default=generate_uuid)
    user_id = Column(String, ForeignKey("users.id"), nullable=False, index=True)
    title = Column(String, default="New Conversation")
    created_at = Column(DateTime, default=utc_now)
    updated_at = Column(DateTime, default=utc_now, onupdate=utc_now)

    # Relationships
    user = relationship("User", back_populates="conversations")
    messages = relationship(
        "Message",
        back_populates="conversation",
        cascade="all, delete-orphan",
        order_by="Message.created_at",
    )
    executions = relationship(
        "Execution", back_populates="conversation", cascade="all, delete-orphan"
    )


class Message(Base):
    __tablename__ = "messages"

    id = Column(String, primary_key=True, default=generate_uuid)
    conversation_id = Column(
        String, ForeignKey("conversations.id"), nullable=False, index=True
    )
    role = Column(String, nullable=False)  # "user" | "assistant"
    content = Column(Text, nullable=False)
    sources = Column(
        JSON, nullable=True
    )  # List of source objects for assistant messages
    execution_id = Column(String, ForeignKey("executions.id"), nullable=True)
    created_at = Column(DateTime, default=utc_now)

    # Relationships
    conversation = relationship("Conversation", back_populates="messages")
    execution = relationship("Execution", back_populates="message")


# ═════════════════════════════════════════════════════════════════════
# EXECUTION — A single question-answering run
# ═════════════════════════════════════════════════════════════════════
class Execution(Base):
    __tablename__ = "executions"

    id = Column(String, primary_key=True, default=generate_uuid)
    conversation_id = Column(
        String, ForeignKey("conversations.id"), nullable=False, index=True
    )
    question = Column(Text, nullable=False)
    time_budget_minutes = Column(Integer, nullable=False)
    status = Column(
        String, default="pending"
    )  # pending → section-2 lifecycle states (created … cancelled) → completed | failed | failed_partial | cancelled
    problem_type = Column(
        String, nullable=True
    )  # math | coding | research | general | multi-step
    complexity = Column(String, nullable=True)  # low | medium | high
    final_answer = Column(Text, nullable=True)
    final_sources = Column(JSON, nullable=True)
    consensus_score = Column(Float, nullable=True)
    total_tokens_used = Column(Integer, default=0)
    total_searches_used = Column(Integer, default=0)
    agent_count = Column(Integer, default=0)
    debate_rounds = Column(Integer, default=0)
    started_at = Column(DateTime, nullable=True)
    completed_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=utc_now)

    # Relationships
    conversation = relationship("Conversation", back_populates="executions")
    message = relationship("Message", back_populates="execution", uselist=False)
    agent_runs = relationship(
        "AgentRun", back_populates="execution", cascade="all, delete-orphan"
    )
    events = relationship(
        "ExecutionEvent",
        back_populates="execution",
        cascade="all, delete-orphan",
        order_by="ExecutionEvent.seq",
    )
    debate_round_records = relationship(
        "DebateRound", back_populates="execution", cascade="all, delete-orphan"
    )
    consensus_events = relationship(
        "ConsensusEvent", back_populates="execution", cascade="all, delete-orphan"
    )


# ═════════════════════════════════════════════════════════════════════
# AGENT RUNS — Each agent's participation in an execution
# ═════════════════════════════════════════════════════════════════════
class AgentRun(Base):
    __tablename__ = "agent_runs"

    id = Column(String, primary_key=True, default=generate_uuid)
    execution_id = Column(
        String, ForeignKey("executions.id"), nullable=False, index=True
    )
    agent_type = Column(
        String, nullable=False
    )  # solver | researcher | critic | synthesizer
    role_description = Column(String, nullable=True)
    model = Column(String, nullable=False)
    provider = Column(
        String, nullable=False
    )  # gemini | groq | cerebras | openrouter | huggingface
    input_tokens = Column(Integer, default=0)
    output_tokens = Column(Integer, default=0)
    status = Column(String, default="active")  # active | completed | failed | timeout
    confidence = Column(Float, nullable=True)
    started_at = Column(DateTime, default=utc_now)
    completed_at = Column(DateTime, nullable=True)

    # Relationships
    execution = relationship("Execution", back_populates="agent_runs")
    agent_messages = relationship(
        "AgentMessage", back_populates="agent_run", cascade="all, delete-orphan"
    )


# ═════════════════════════════════════════════════════════════════════
# AGENT MESSAGES — What each agent said in each round
# ═════════════════════════════════════════════════════════════════════
class AgentMessage(Base):
    __tablename__ = "agent_messages"

    id = Column(String, primary_key=True, default=generate_uuid)
    agent_run_id = Column(
        String, ForeignKey("agent_runs.id"), nullable=False, index=True
    )
    round_number = Column(Integer, nullable=False)
    message_type = Column(
        String, nullable=False
    )  # solution | critique | evidence | vote | synthesis
    content = Column(Text, nullable=False)
    position = Column(Text, nullable=True)
    evidence = Column(JSON, nullable=True)
    confidence = Column(Float, nullable=True)
    supports = Column(JSON, nullable=True)  # list of agent_run_ids
    disagrees_with = Column(JSON, nullable=True)  # list of agent_run_ids
    created_at = Column(DateTime, default=utc_now)

    # Relationships
    agent_run = relationship("AgentRun", back_populates="agent_messages")


# ═════════════════════════════════════════════════════════════════════
# DEBATE ROUNDS
# ═════════════════════════════════════════════════════════════════════
class DebateRound(Base):
    __tablename__ = "debate_rounds"

    id = Column(String, primary_key=True, default=generate_uuid)
    execution_id = Column(
        String, ForeignKey("executions.id"), nullable=False, index=True
    )
    round_number = Column(Integer, nullable=False)
    round_type = Column(
        String, nullable=False
    )  # independent | cross_examination | research | resolution | consensus
    summary = Column(Text, nullable=True)
    consensus_score = Column(Float, nullable=True)
    created_at = Column(DateTime, default=utc_now)

    # Relationships
    execution = relationship("Execution", back_populates="debate_round_records")


# ═════════════════════════════════════════════════════════════════════
# CONSENSUS EVENTS
# ═════════════════════════════════════════════════════════════════════
class ConsensusEvent(Base):
    __tablename__ = "consensus_events"

    id = Column(String, primary_key=True, default=generate_uuid)
    execution_id = Column(
        String, ForeignKey("executions.id"), nullable=False, index=True
    )
    round_number = Column(Integer, nullable=False)
    consensus_score = Column(Float, nullable=False)
    agreement_count = Column(Integer, default=0)
    disagreement_count = Column(Integer, default=0)
    decision = Column(String, nullable=False)  # FINALIZE | DEBATE | ADVERSARIAL | FORCE_FINALIZE
    reasoning = Column(Text, nullable=True)
    created_at = Column(DateTime, default=utc_now)

    # Relationships
    execution = relationship("Execution", back_populates="consensus_events")


# ═════════════════════════════════════════════════════════════════════
# EXECUTION EVENTS — Persisted progress-event log (WORKFLOW section 8)
# ═════════════════════════════════════════════════════════════════════
class ExecutionEvent(Base):
    """One sequenced progress event per execution.

    Written by the API layer as events broadcast (best-effort); powers
    WebSocket replay (?after_seq=N) and GET /events. Payloads are short
    human-readable summaries — never keys, never chain-of-thought
    (see src/api/events.py sanitize_payload).
    """

    __tablename__ = "execution_events"

    id = Column(String, primary_key=True, default=generate_uuid)
    execution_id = Column(
        String, ForeignKey("executions.id"), nullable=False, index=True
    )
    seq = Column(Integer, nullable=False)  # dense per-execution order, starts at 1
    type = Column(String, nullable=False, index=True)  # dotted §8 name
    payload = Column(JSON, nullable=True)  # sanitized event data dict
    created_at = Column(DateTime, default=utc_now)

    __table_args__ = (
        # One writer (the orchestrator recorder) assigns seqs, so this
        # only guards against double-persist bugs, never normal traffic.
        UniqueConstraint("execution_id", "seq"),
    )

    # Relationships
    execution = relationship("Execution", back_populates="events")


# ═════════════════════════════════════════════════════════════════════
# QUOTA USAGE — Daily per-key counters (survive restarts)
# ═════════════════════════════════════════════════════════════════════
class QuotaUsage(Base):
    """Calls/tokens spent per (provider, key fingerprint, day).

    The fingerprint is a salted SHA-256 prefix (see providers/quota.py) —
    raw keys are never stored here.
    """

    __tablename__ = "quota_usage"

    provider = Column(String, primary_key=True)
    key_fingerprint = Column(String, primary_key=True)
    day = Column(String, primary_key=True)  # YYYY-MM-DD
    count = Column(Integer, default=0)
    tokens = Column(Integer, default=0)
    updated_at = Column(DateTime, default=utc_now, onupdate=utc_now)


# ═════════════════════════════════════════════════════════════════════
# SOURCES & CITATIONS
# ═════════════════════════════════════════════════════════════════════
class Source(Base):
    __tablename__ = "sources"

    id = Column(String, primary_key=True, default=generate_uuid)
    execution_id = Column(
        String, ForeignKey("executions.id"), nullable=False, index=True
    )
    url = Column(String, nullable=True)
    title = Column(String, nullable=True)
    snippet = Column(Text, nullable=True)
    credibility_score = Column(Float, nullable=True)
    used_in_final = Column(Boolean, default=False)
    created_at = Column(DateTime, default=utc_now)
