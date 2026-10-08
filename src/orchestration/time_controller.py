"""
Assembly — Time controller: deadlines, per-call timeouts, task tracking.

Single home for wall-clock enforcement (docs/WORKFLOW.md sections 2/4):

- ``ExecState`` / ``StateMachine`` — the section 2 execution lifecycle.
  Every transition is validated; CANCELLED and FAILED_PARTIAL are
  reachable from any non-terminal state, exactly as the diagram shows.
- ``Deadline`` — remaining-time math against an injectable clock, the
  synthesis reserve (``max(25 s, 12% of budget)`` from capacity), round
  gating, per-call timeouts, and user-cancellation flagging.
- ``TaskTracker`` — named-task registry with bulk cancel + drain so a
  cancelled phase never leaves orphaned tasks behind.

Only quota COUNTS-adjacent numbers flow here (seconds, estimates) —
never keys. Clocks are injectable so tests use a FakeClock instead of
sleeping.
"""

import asyncio
import time
from collections.abc import Callable, Coroutine
from enum import Enum
from typing import Any, Self

from src.core.logging_config import logger
from src.orchestration.capacity import synth_reserve_seconds

# ── Tunables ──────────────────────────────────────────────────────────

#: Upper bound for any single agent call (straggler backstop).
DEFAULT_CALL_TIMEOUT_S: float = 120.0

#: Floor for derived call timeouts: guards against clock jitter turning a
#: just-barely-room call into an instant-cancel. The hard cutoff itself is
#: enforced by should_synthesize_now()/can_start_round() gating, not here.
MIN_CALL_TIMEOUT_S: float = 1.0

#: Synthesis always gets at least this much of a final window, even past
#: the nominal deadline — a late answer beats no answer.
SYNTH_TIMEOUT_FLOOR_S: float = 5.0


# ── Execution states (docs/WORKFLOW.md section 2) ─────────────────────


class ExecState(str, Enum):
    """Lifecycle states. Values are persisted to Execution.status."""

    CREATED = "created"
    CAPACITY_CHECK = "capacity_check"
    PLANNING = "planning"
    TEAM_READY = "team_ready"
    SOLVING = "solving"
    EVALUATING = "evaluating"
    DEBATING = "debating"
    SYNTHESIZING = "synthesizing"
    COMPLETED = "completed"
    CANCELLED = "cancelled"
    FAILED_PARTIAL = "failed_partial"


_TERMINAL_STATES = frozenset(
    {ExecState.COMPLETED, ExecState.CANCELLED, ExecState.FAILED_PARTIAL}
)

# Abnormal exits reachable from anywhere non-terminal (diagram's ↘ arrow).
_ABNORMAL_EXITS = frozenset({ExecState.CANCELLED, ExecState.FAILED_PARTIAL})

TRANSITIONS: dict[ExecState, frozenset[ExecState]] = {
    ExecState.CREATED: frozenset({ExecState.CAPACITY_CHECK}),
    ExecState.CAPACITY_CHECK: frozenset({ExecState.PLANNING}),
    ExecState.PLANNING: frozenset({ExecState.TEAM_READY}),
    ExecState.TEAM_READY: frozenset({ExecState.SOLVING}),
    ExecState.SOLVING: frozenset({ExecState.EVALUATING}),
    ExecState.EVALUATING: frozenset({ExecState.DEBATING, ExecState.SYNTHESIZING}),
    ExecState.DEBATING: frozenset({ExecState.EVALUATING}),
    ExecState.SYNTHESIZING: frozenset({ExecState.COMPLETED}),
    ExecState.COMPLETED: frozenset(),
    ExecState.CANCELLED: frozenset(),
    ExecState.FAILED_PARTIAL: frozenset(),
}


class InvalidStateTransition(ValueError):
    """An execution tried a lifecycle move the section 2 diagram forbids."""


class StateMachine:
    """Explicit, validated execution-lifecycle tracker (one per execution)."""

    def __init__(self) -> None:
        self.state: ExecState = ExecState.CREATED
        self.history: list[ExecState] = [ExecState.CREATED]

    @property
    def terminal(self) -> bool:
        """True once the execution reached a final state."""
        return self.state in _TERMINAL_STATES

    def can_transition(self, new_state: ExecState) -> bool:
        """Check a move without performing it."""
        if self.terminal:
            return False
        if new_state in _ABNORMAL_EXITS:
            return True
        return new_state in TRANSITIONS[self.state]

    def transition(self, new_state: ExecState | str) -> ExecState:
        """Move to a new state, validating against the section 2 diagram.

        Returns the previous state. Raises InvalidStateTransition on an
        illegal move — a bug in the orchestrator, never user input.
        """
        target = new_state if isinstance(new_state, ExecState) else ExecState(new_state)
        if not self.can_transition(target):
            raise InvalidStateTransition(
                f"Illegal execution transition {self.state.value} → {target.value}"
            )
        previous = self.state
        self.state = target
        self.history.append(target)
        return previous


# ── Clocks (injectable for tests) ─────────────────────────────────────


class FakeClock:
    """Manual clock for tests: no sleeping, fully deterministic."""

    def __init__(self, start: float = 0.0) -> None:
        self.now_seconds = start

    def __call__(self) -> float:
        return self.now_seconds

    def advance(self, seconds: float) -> float:
        """Move the clock forward; returns the new time."""
        self.now_seconds += seconds
        return self.now_seconds


# ── Deadline ──────────────────────────────────────────────────────────


class Deadline:
    """Wall-clock budget for one execution.

    Args:
        budget_seconds: total wall-clock budget for the run.
        clock: time source; defaults to time.monotonic. Tests pass FakeClock.
        synth_reserve_seconds: time kept for final synthesis; defaults to
            the capacity formula max(25 s, 12% of budget).
        min_call_timeout / default_call_timeout: bounds for timeout_for_call.
    """

    def __init__(
        self,
        budget_seconds: float,
        clock: Callable[[], float] | None = None,
        synth_reserve_seconds: float | None = None,
        min_call_timeout: float = MIN_CALL_TIMEOUT_S,
        default_call_timeout: float = DEFAULT_CALL_TIMEOUT_S,
    ) -> None:
        self._clock = clock or time.monotonic
        self.budget_seconds = max(0.0, budget_seconds)
        self.started_at = self._clock()
        self.deadline_at = self.started_at + self.budget_seconds
        if synth_reserve_seconds is None:
            synth_reserve_seconds = synth_reserve_seconds_capacity(self.budget_seconds)
        self.synth_reserve = max(0.0, synth_reserve_seconds)
        self.min_call_timeout = min_call_timeout
        self.default_call_timeout = default_call_timeout
        self._cancel_requested = False

    # ── Reading the clock ──

    def remaining(self) -> float:
        """Seconds left until the deadline (never negative)."""
        return max(0.0, self.deadline_at - self._clock())

    def elapsed(self) -> float:
        """Seconds since the execution started."""
        return max(0.0, self._clock() - self.started_at)

    @property
    def expired(self) -> bool:
        """True once the wall-clock budget is spent."""
        return self.remaining() <= 0.0

    # ── Hard-cutoff gating (WORKFLOW section 4) ──

    def should_synthesize_now(self) -> bool:
        """Stop launching work and go to synthesis with current positions."""
        return self.remaining() <= self.synth_reserve

    def can_start_round(self, estimated_seconds: float) -> bool:
        """A new round may start only with room for it AND synthesis."""
        return self.remaining() >= estimated_seconds + self.synth_reserve

    def timeout_for_call(self, estimated_seconds: float | None = None) -> float:
        """Per-call timeout derived from remaining time.

        Bounded above by the estimate (or the straggler backstop) and by
        the usable room (remaining minus synthesis reserve), floored so
        clock jitter can't turn a viable call into an instant-cancel.
        Callers must still gate launches on can_start_round(); this only
        bounds calls already in flight.
        """
        base = (
            estimated_seconds
            if estimated_seconds is not None
            else self.default_call_timeout
        )
        room = self.remaining() - self.synth_reserve
        return max(self.min_call_timeout, min(base, room))

    def synthesis_timeout(self) -> float:
        """Timeout for the final synthesis call: whatever is left, floored."""
        return max(SYNTH_TIMEOUT_FLOOR_S, self.remaining())

    # ── User cancellation ──

    def request_cancel(self) -> None:
        """Flag user cancellation; checked at phase boundaries."""
        self._cancel_requested = True

    @property
    def cancel_requested(self) -> bool:
        """True once the user asked to stop this execution."""
        return self._cancel_requested

    def raise_if_cancelled(self) -> None:
        """Raise CancelledError at phase boundaries when flagged."""
        if self._cancel_requested:
            raise asyncio.CancelledError("execution cancelled by user")


def synth_reserve_seconds_capacity(budget_seconds: float) -> float:
    """Synthesis reserve via the single capacity formula (minutes-based)."""
    return synth_reserve_seconds(budget_seconds / 60.0)


def synth_reserve_seconds_capacity(budget_seconds: float) -> float:
    """Synthesis reserve via the single capacity formula (minutes-based)."""
    return synth_reserve_seconds(budget_seconds / 60.0)


# ── Task tracking (no orphaned tasks) ─────────────────────────────────


class TaskTracker:
    """Named-task registry with bulk cancel + drain.

    Typical use::

        async with TaskTracker("exec-123") as tracker:
            tasks = [tracker.create(coro(), name=...) for ...]
            results = await asyncio.gather(*tasks, return_exceptions=True)

    Exiting the context cancels stragglers and awaits them, so no task
    outlives its phase — even under user cancellation or timeouts.
    """

    def __init__(self, owner: str = "") -> None:
        self.owner = owner
        self._tasks: set[asyncio.Task] = set()

    def create(
        self, coro: Coroutine[Any, Any, Any], *, name: str | None = None
    ) -> asyncio.Task:
        """Schedule a coroutine and track it; auto-untracks on completion."""
        task = asyncio.create_task(coro, name=name)
        self._tasks.add(task)
        task.add_done_callback(self._tasks.discard)
        return task

    def pending(self) -> list[asyncio.Task]:
        """Tracked tasks not yet done (snapshot)."""
        return [t for t in self._tasks if not t.done()]

    def __len__(self) -> int:
        return len(self.pending())

    def cancel_all(self) -> int:
        """Request cancellation of every tracked task; returns count."""
        pending = self.pending()
        for task in pending:
            task.cancel()
        if pending:
            logger.info(
                f"TimeCtl │ Cancelled {len(pending)} in-flight task(s)"
                + (f" for {self.owner}" if self.owner else "")
            )
        return len(pending)

    async def drain(self) -> None:
        """Await every tracked task to completion (errors swallowed).

        Must be called from a context that tolerates awaiting: after a
        parent cancellation this still works because gather() with
        return_exceptions=True absorbs child cancellations.
        """
        tasks = list(self._tasks)
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)

    async def __aenter__(self) -> Self:
        return self

    async def __aexit__(self, *args: object) -> None:
        self.cancel_all()
        await self.drain()
