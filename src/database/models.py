"""Assembly — Database Models (desktop/dev SQLite only).

Web mode is stateless and never touches these tables. No User table:
there are no accounts. Desktop keeps local run history only.
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
# EXECUTION — A single question-answering run (local history only)
# ═════════════════════════════════════════════════════════════════════
class Execution(Base):
    __tablename__ = "executions"

    id = Column(String, primary_key=True, default=generate_uuid)
    question = Column(Text, nullable=False)
    time_budget_minutes = Column(Integer, nullable=False)
    status = Column(String, default="pending")
    problem_type = Column(String, nullable=True)
    complexity = Column(String, nullable=True)
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
# AGENT RUNS
# ═════════════════════════════════════════════════════════════════════
class AgentRun(Base):
    __tablename__ = "agent_runs"

    id = Column(String, primary_key=True, default=generate_uuid)
    execution_id = Column(String, ForeignKey("executions.id"), nullable=False, index=True)
    agent_type = Column(String, nullable=False)
    role_description = Column(String, nullable=True)
    model = Column(String, nullable=False)
    provider = Column(String, nullable=False)
    input_tokens = Column(Integer, default=0)
    output_tokens = Column(Integer, default=0)
    status = Column(String, default="active")
    confidence = Column(Float, nullable=True)
    started_at = Column(DateTime, default=utc_now)
    completed_at = Column(DateTime, nullable=True)

    execution = relationship("Execution", back_populates="agent_runs")
    agent_messages = relationship(
        "AgentMessage", back_populates="agent_run", cascade="all, delete-orphan"
    )


# ═════════════════════════════════════════════════════════════════════
# AGENT MESSAGES
# ═════════════════════════════════════════════════════════════════════
class AgentMessage(Base):
    __tablename__ = "agent_messages"

    id = Column(String, primary_key=True, default=generate_uuid)
    agent_run_id = Column(String, ForeignKey("agent_runs.id"), nullable=False, index=True)
    round_number = Column(Integer, nullable=False)
    message_type = Column(String, nullable=False)
    content = Column(Text, nullable=False)
    position = Column(Text, nullable=True)
    evidence = Column(JSON, nullable=True)
    confidence = Column(Float, nullable=True)
    supports = Column(JSON, nullable=True)
    disagrees_with = Column(JSON, nullable=True)
    created_at = Column(DateTime, default=utc_now)

    agent_run = relationship("AgentRun", back_populates="agent_messages")


# ═════════════════════════════════════════════════════════════════════
# DEBATE ROUNDS
# ═════════════════════════════════════════════════════════════════════
class DebateRound(Base):
    __tablename__ = "debate_rounds"

    id = Column(String, primary_key=True, default=generate_uuid)
    execution_id = Column(String, ForeignKey("executions.id"), nullable=False, index=True)
    round_number = Column(Integer, nullable=False)
    round_type = Column(String, nullable=False)
    summary = Column(Text, nullable=True)
    consensus_score = Column(Float, nullable=True)
    created_at = Column(DateTime, default=utc_now)

    execution = relationship("Execution", back_populates="debate_round_records")


# ═════════════════════════════════════════════════════════════════════
# CONSENSUS EVENTS
# ═════════════════════════════════════════════════════════════════════
class ConsensusEvent(Base):
    __tablename__ = "consensus_events"

    id = Column(String, primary_key=True, default=generate_uuid)
    execution_id = Column(String, ForeignKey("executions.id"), nullable=False, index=True)
    round_number = Column(Integer, nullable=False)
    consensus_score = Column(Float, nullable=False)
    agreement_count = Column(Integer, default=0)
    disagreement_count = Column(Integer, default=0)
    decision = Column(String, nullable=False)
    reasoning = Column(Text, nullable=True)
    created_at = Column(DateTime, default=utc_now)

    execution = relationship("Execution", back_populates="consensus_events")


# ═════════════════════════════════════════════════════════════════════
# EXECUTION EVENTS (desktop persistence only; web uses in-memory replay)
# ═════════════════════════════════════════════════════════════════════
class ExecutionEvent(Base):
    __tablename__ = "execution_events"

    id = Column(String, primary_key=True, default=generate_uuid)
    execution_id = Column(String, ForeignKey("executions.id"), nullable=False, index=True)
    seq = Column(Integer, nullable=False)
    type = Column(String, nullable=False, index=True)
    payload = Column(JSON, nullable=True)
    created_at = Column(DateTime, default=utc_now)

    __table_args__ = (UniqueConstraint("execution_id", "seq"),)

    execution = relationship("Execution", back_populates="events")


# ═════════════════════════════════════════════════════════════════════
# QUOTA USAGE (desktop persistence; web uses memory only)
# ═════════════════════════════════════════════════════════════════════
class QuotaUsage(Base):
    """Calls/tokens spent per (provider, key fingerprint, model, day)."""

    __tablename__ = "quota_usage"

    provider = Column(String, primary_key=True)
    key_fingerprint = Column(String, primary_key=True)
    day = Column(String, primary_key=True)
    model_id = Column(String, primary_key=True, default="")
    count = Column(Integer, default=0)
    tokens = Column(Integer, default=0)
    updated_at = Column(DateTime, default=utc_now, onupdate=utc_now)


# ═════════════════════════════════════════════════════════════════════
# SOURCES & CITATIONS
# ═════════════════════════════════════════════════════════════════════
class Source(Base):
    __tablename__ = "sources"

    id = Column(String, primary_key=True, default=generate_uuid)
    execution_id = Column(String, ForeignKey("executions.id"), nullable=False, index=True)
    url = Column(String, nullable=True)
    title = Column(String, nullable=True)
    snippet = Column(Text, nullable=True)
    credibility_score = Column(Float, nullable=True)
    used_in_final = Column(Boolean, default=False)
    created_at = Column(DateTime, default=utc_now)
