"""
Assembly — Shared Workspace / Event Bus

In-memory event store where agents publish findings and read
others' conclusions (PRD Section 26/30).
"""

import asyncio
from typing import List, Dict, Any, Optional, Callable
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum

from src.core.logging_config import logger


class EventType(str, Enum):
    SOLUTION = "solution"
    CRITIQUE = "critique"
    EVIDENCE = "evidence"
    RESEARCH_RESULT = "research_result"
    CONSENSUS_VOTE = "consensus_vote"
    STATUS_UPDATE = "status_update"


@dataclass
class WorkspaceEvent:
    """A single event published to the shared workspace."""
    event_type: EventType
    agent_id: str
    execution_id: str
    round_number: int
    data: Dict[str, Any]
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    def to_dict(self) -> dict:
        return {
            "event_type": self.event_type.value,
            "agent_id": self.agent_id,
            "execution_id": self.execution_id,
            "round_number": self.round_number,
            "data": self.data,
            "timestamp": self.timestamp.isoformat(),
        }


class SharedWorkspace:
    """
    In-memory event bus for agent communication.
    
    Agents publish structured events (solutions, critiques, evidence)
    and read events from other agents. The workspace is scoped per execution.
    
    Advantages over direct API-to-API:
    - Better observability
    - Easier retries
    - Better parallel execution
    - Easier persistence & debugging
    - Provider independence
    """

    def __init__(self):
        self._events: Dict[str, List[WorkspaceEvent]] = {}  # execution_id → events
        self._listeners: Dict[str, List[Callable]] = {}  # execution_id → callbacks
        self._lock = asyncio.Lock()

    async def publish(self, event: WorkspaceEvent):
        """Publish an event to the workspace."""
        async with self._lock:
            if event.execution_id not in self._events:
                self._events[event.execution_id] = []
            self._events[event.execution_id].append(event)

        # Notify listeners
        for callback in self._listeners.get(event.execution_id, []):
            try:
                await callback(event)
            except Exception as e:
                logger.error(f"Workspace │ Listener error: {e}")

    def subscribe(self, execution_id: str, callback: Callable):
        """Subscribe to events for a specific execution."""
        if execution_id not in self._listeners:
            self._listeners[execution_id] = []
        self._listeners[execution_id].append(callback)

    def get_events(
        self,
        execution_id: str,
        event_type: Optional[EventType] = None,
        round_number: Optional[int] = None,
        exclude_agent: Optional[str] = None,
    ) -> List[WorkspaceEvent]:
        """
        Read events from the workspace, optionally filtered.
        
        Args:
            execution_id: Which execution's events to read.
            event_type: Filter by event type.
            round_number: Filter by round.
            exclude_agent: Exclude events from a specific agent (to prevent self-review).
        """
        events = self._events.get(execution_id, [])

        if event_type:
            events = [e for e in events if e.event_type == event_type]
        if round_number is not None:
            events = [e for e in events if e.round_number == round_number]
        if exclude_agent:
            events = [e for e in events if e.agent_id != exclude_agent]

        return events

    def get_latest_solutions(self, execution_id: str) -> List[WorkspaceEvent]:
        """Get the most recent solution from each agent."""
        events = self.get_events(execution_id, EventType.SOLUTION)
        # Keep only the latest per agent
        latest: Dict[str, WorkspaceEvent] = {}
        for e in events:
            latest[e.agent_id] = e
        return list(latest.values())

    def cleanup(self, execution_id: str):
        """Remove all data for a completed execution."""
        self._events.pop(execution_id, None)
        self._listeners.pop(execution_id, None)


# ── Singleton ────────────────────────────────────────────────────────
workspace = SharedWorkspace()
