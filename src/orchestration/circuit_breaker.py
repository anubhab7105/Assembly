"""
Assembly — per-run circuit breaker for repeatedly failing models.

After one model fails TRIP_THRESHOLD times on one role within a single
execution, the breaker OPENS for that (model, role) pair: retries and
mid-run reroutes skip it in favour of a healthy model. Counts live on
the instance (created fresh per execution inside Orchestrator.execute via
AgentManager), so trips never leak across runs. Names and counts only —
never keys or prompt content.
"""

import time
from dataclasses import dataclass, field

#: Failures of one model on one role before the breaker opens for it.
TRIP_THRESHOLD: int = 2


@dataclass
class CircuitBreaker:
    """Trip counting for (model, role) pairs within one execution."""

    threshold: int = TRIP_THRESHOLD
    _failures: dict[tuple[str, str], int] = field(default_factory=dict)
    trips: list[dict[str, object]] = field(default_factory=list)

    def record_failure(self, model: str, role: str) -> bool:
        """Count one failure; True when this call newly trips the breaker."""
        key = (model or "unknown", role or "unknown")
        count = self._failures.get(key, 0) + 1
        self._failures[key] = count
        if count == max(1, self.threshold):
            self.trips.append({"model": key[0], "role": key[1], "failures": count})
            return True
        return False

    def is_open(self, model: str, role: str) -> bool:
        """True once (model, role) has failed threshold times or more."""
        return self._failures.get((model or "unknown", role or "unknown"), 0) >= max(
            1, self.threshold
        )

    def failure_count(self, model: str, role: str) -> int:
        """Failures recorded so far for (model, role)."""
        return self._failures.get((model or "unknown", role or "unknown"), 0)

    def failures_for_role(self, role: str) -> int:
        """Total failures across all models for one role (research health)."""
        return sum(count for (_model, r), count in self._failures.items() if r == role)


#: How long cross-run failure memory lasts: a model that failed recently
#: stays avoided; after 30 quiet minutes it gets another chance.
CROSS_RUN_TTL_SECONDS: float = 1800.0


class CrossRunHealth:
    """In-process (model, role) failure memory shared across executions.

    Same trip threshold as the per-run breaker, but counts survive the
    run that recorded them until CROSS_RUN_TTL_SECONDS passes without a
    new failure. Purely in-process (a module-level dict): a restart
    forgets everything, which is the safe direction — worst case is one
    wasted call per model/role per process lifetime. Holds names and
    counts only, never keys or content.
    """

    def __init__(
        self,
        ttl_seconds: float = CROSS_RUN_TTL_SECONDS,
        threshold: int = TRIP_THRESHOLD,
    ) -> None:
        self._ttl = max(0.0, ttl_seconds)
        self._threshold = max(1, threshold)
        self._failures: dict[tuple[str, str], int] = {}
        self._last: dict[tuple[str, str], float] = {}

    def record_failure(self, model: str, role: str) -> bool:
        """Count one failure; True when (model, role) is now avoided."""
        key = (model or "unknown", role or "unknown")
        self._failures[key] = self._failures.get(key, 0) + 1
        self._last[key] = time.monotonic()
        return self.is_avoided(model, role)

    def is_avoided(self, model: str, role: str) -> bool:
        """True when (model, role) failed threshold times within the TTL."""
        key = (model or "unknown", role or "unknown")
        if self._failures.get(key, 0) < self._threshold:
            return False
        if time.monotonic() - self._last.get(key, 0.0) >= self._ttl:
            self._failures.pop(key, None)
            self._last.pop(key, None)
            return False
        return True

    def reset(self) -> None:
        """Drop all memory (tests; process restarts do this implicitly)."""
        self._failures.clear()
        self._last.clear()


_cross_run_health = CrossRunHealth()


def cross_run_health() -> CrossRunHealth:
    """Process-wide failure memory singleton."""
    return _cross_run_health


def reset_cross_run_health() -> None:
    """Clear the singleton (tests only; restarts do this implicitly)."""
    _cross_run_health.reset()
