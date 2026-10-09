"""
Assembly — Budget Controller

Tracks and enforces time, token, agent, and search budgets
per execution (PRD Section 23).
"""

import time
from dataclasses import dataclass, field


@dataclass
class BudgetState:
    """Current budget consumption for an execution."""
    # Limits
    time_budget_seconds: float = 300.0
    max_tokens: int = 100_000
    max_agents: int = 6
    max_debate_rounds: int = 8
    max_searches: int = 20

    # Current usage
    tokens_used: int = 0
    agents_created: int = 0
    debate_rounds_completed: int = 0
    searches_used: int = 0
    start_time: float = field(default_factory=time.time)

    @property
    def elapsed_seconds(self) -> float:
        return time.time() - self.start_time

    @property
    def remaining_seconds(self) -> float:
        return max(0, self.time_budget_seconds - self.elapsed_seconds)

    @property
    def remaining_minutes(self) -> float:
        return self.remaining_seconds / 60

    @property
    def time_fraction_used(self) -> float:
        return min(1.0, self.elapsed_seconds / self.time_budget_seconds)

    @property
    def token_fraction_used(self) -> float:
        return min(1.0, self.tokens_used / self.max_tokens) if self.max_tokens > 0 else 0


class BudgetController:
    """
    Enforces execution budgets.
    
    Tracks time, tokens, agents, debate rounds, and web searches.
    Provides decision signals to the orchestrator.
    """

    # Reserve time for final synthesis
    SYNTHESIS_RESERVE_SECONDS = 30.0

    def __init__(self, time_budget_minutes: int):
        # Determine budget allocations based on time
        budget_config = self._get_budget_config(time_budget_minutes)

        self.state = BudgetState(
            time_budget_seconds=time_budget_minutes * 60,
            max_tokens=budget_config["max_tokens"],
            max_agents=budget_config["max_agents"],
            max_debate_rounds=budget_config["max_debate_rounds"],
            max_searches=budget_config["max_searches"],
        )

    @staticmethod
    def token_cap_for_tier(minutes: int) -> int:
        """Max execution tokens for a tier (single source for the cap).

        The capacity planner imports this (no cycle: this module depends
        only on the stdlib) so p90 token estimates gate tier selection.
        """
        if minutes <= 3:
            return 50_000
        if minutes <= 5:
            return 80_000
        if minutes <= 10:
            return 150_000
        return 250_000

    def _get_budget_config(self, minutes: int) -> dict:
        """
        Determine budget allocations based on time budget.
        
        These are illustrative strategies, not hard-coded rules (PRD Section 7.4).
        max_debate_rounds is a CEILING: the consensus engine stops early via
        FINALIZE as soon as agreement is strong; extra rounds run only while
        consensus says DEBATE/ADVERSARIAL and time/quota remain.
        """
        if minutes <= 3:
            return {
                "max_tokens": BudgetController.token_cap_for_tier(3),
                "max_agents": 3,
                "max_debate_rounds": 1,
                "max_searches": 5,
            }
        elif minutes <= 5:
            return {
                "max_tokens": BudgetController.token_cap_for_tier(5),
                "max_agents": 4,
                "max_debate_rounds": 3,
                "max_searches": 10,
            }
        elif minutes <= 10:
            return {
                "max_tokens": BudgetController.token_cap_for_tier(10),
                "max_agents": 5,
                "max_debate_rounds": 5,
                "max_searches": 20,
            }
        else:  # 15 minutes
            return {
                "max_tokens": BudgetController.token_cap_for_tier(15),
                "max_agents": 6,
                "max_debate_rounds": 8,
                "max_searches": 30,
            }

    def record_tokens(self, count: int):
        """Record token usage."""
        self.state.tokens_used += count

    def record_agent_created(self):
        """Record a new agent being created."""
        self.state.agents_created += 1

    def record_debate_round(self):
        """Record a completed debate round."""
        self.state.debate_rounds_completed += 1

    def record_search(self, count: int = 1):
        """Record web search usage."""
        self.state.searches_used += count

    # ── Decision Methods ─────────────────────────────────────────────

    def can_create_agent(self) -> bool:
        """Check if we can add another agent."""
        return (
            self.state.agents_created < self.state.max_agents
            and not self.is_time_expired()
        )

    def can_debate(self) -> bool:
        """Check if another debate round is allowed."""
        return (
            self.state.debate_rounds_completed < self.state.max_debate_rounds
            and self.has_time_for_debate()
            and not self.is_token_limited()
        )

    def can_search(self) -> bool:
        """Check if web search budget remains."""
        return self.state.searches_used < self.state.max_searches

    def has_time_for_debate(self) -> bool:
        """Check if there's enough time for another debate round + synthesis."""
        return self.state.remaining_seconds > self.SYNTHESIS_RESERVE_SECONDS + 30

    def is_time_expired(self) -> bool:
        """Check if the hard time budget has been exceeded."""
        return self.state.remaining_seconds <= 0

    def is_near_deadline(self) -> bool:
        """Check if we should stop launching new work and begin synthesis."""
        return self.state.remaining_seconds <= self.SYNTHESIS_RESERVE_SECONDS

    def is_token_limited(self) -> bool:
        """Check if we're close to the token budget."""
        return self.state.token_fraction_used >= 0.9

    def should_force_synthesis(self) -> bool:
        """Check if we MUST move to synthesis immediately."""
        return self.is_near_deadline() or self.is_time_expired() or self.is_token_limited()

    def get_status(self) -> dict:
        """Get current budget status for progress reporting."""
        return {
            "time_remaining_seconds": round(self.state.remaining_seconds, 1),
            "time_remaining_formatted": self._format_time(self.state.remaining_seconds),
            "time_fraction_used": round(self.state.time_fraction_used, 2),
            "tokens_used": self.state.tokens_used,
            "token_fraction_used": round(self.state.token_fraction_used, 2),
            "agents_created": self.state.agents_created,
            "max_agents": self.state.max_agents,
            "debate_rounds": self.state.debate_rounds_completed,
            "max_debate_rounds": self.state.max_debate_rounds,
            "searches_used": self.state.searches_used,
            "max_searches": self.state.max_searches,
        }

    @staticmethod
    def _format_time(seconds: float) -> str:
        """Format seconds as MM:SS."""
        mins = int(seconds) // 60
        secs = int(seconds) % 60
        return f"{mins:02d}:{secs:02d}"
