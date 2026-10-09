"""
Assembly — Debate Manager

Runs cross-agent debate rounds. Each agent reviews others' conclusions
and produces critiques. Enforces that every round adds value (PRD Section 7.3).

Implements context compression to prevent O(N²) context window bloat
when teams are large or debates run for many rounds.
"""

import asyncio
from typing import Any

from src.agents.base_agent import AgentOutput, BaseAgent
from src.core.logging_config import logger
from src.orchestration.time_controller import TaskTracker
from src.orchestration.workspace import EventType, WorkspaceEvent, workspace


class DebateManager:
    """
    Manages multi-round agent debates.

    In each round:
    1. Each agent sees ALL other agents' latest positions (compressed)
    2. Each agent produces a critique / updated position
    3. Results are published to the shared workspace

    Every round must resolve a disagreement, add evidence,
    improve a solution, remove an error, or increase confidence —
    not produce conversational filler (PRD Section 7.3).
    """

    # Context compression limits (fallback when a model's context is unknown)
    MAX_POSITION_CHARS = 1500  # Truncate long positions
    MAX_EVIDENCE_ITEMS = 3  # Keep only top evidence points
    MAX_REASONING_CHARS = 500  # Truncate reasoning
    # Token budget shaping for known contexts (chars ≈ 4 per token).
    MAX_DEBATE_PROMPT_TOKENS = 12000  # cap critique context even for huge windows
    ANSWER_RESERVE_TOKENS = 4500  # max_tokens (4096) + margin for the reply
    PROMPT_OVERHEAD_TOKENS = 500  # question + instructions around the context
    MIN_PER_OTHER_CHARS = 1200  # floor so a critique stays usable
    CHARS_PER_TOKEN = 4

    def __init__(self, execution_id: str, config: Any = None) -> None:
        self.execution_id = execution_id
        # ModelsConfig for per-recipient context budgets; None keeps the
        # legacy fixed caps (used by older call sites and unit tests).
        self._config = config

    async def run_debate_round(
        self,
        agents: list[BaseAgent],
        current_outputs: list[AgentOutput],
        question: str,
        round_number: int,
        timeout_s: float | None = None,
        tracker: TaskTracker | None = None,
    ) -> list[AgentOutput]:
        """
        Run one debate round: all agents review each other's work in parallel.

        Args:
            agents: Active agent instances.
            current_outputs: Each agent's latest output.
            question: Original user question.
            round_number: Current round number.
            timeout_s: per-critique wall-clock bound (stragglers become
                stale carry-forwards instead of hanging the run).
            tracker: task registry for bulk cancel + leak detection.

        Returns:
            Updated list of AgentOutput after debate.
        """
        logger.info(f"Debate  │ Round {round_number} — {len(agents)} agents debating")

        # Previous outputs by agent for stale carry-forward on failure.
        output_map = {o.agent_id: o for o in current_outputs}

        own_tracker = (
            tracker
            if tracker is not None
            else TaskTracker(owner=f"{self.execution_id}:debate-{round_number}")
        )

        # Each agent critiques all others IN PARALLEL, compressed to fit
        # THAT agent's own model context (per-recipient budgets).
        tasks = []
        for agent in agents:
            others_raw = [o for o in current_outputs if o.agent_id != agent.agent_id]
            if others_raw:
                per_other = self._per_other_chars(agent, len(others_raw))
                others = self._compress_outputs(others_raw, per_other)
                coro = self._agent_critique(
                    agent, question, others, round_number, timeout_s
                )
            else:
                # No others to critique — re-run independently
                coro = self._timed_run(agent, question, timeout_s)
            tasks.append(
                own_tracker.create(
                    coro, name=f"assembly:{self.execution_id}:{agent.agent_id}"
                )
            )

        # Run all critiques concurrently
        try:
            results = await asyncio.gather(*tasks, return_exceptions=True)
        finally:
            # No orphaned tasks: stragglers are awaited here even when this
            # task itself is cancelled (user cancel / deadline).
            await own_tracker.drain()

        # Collect valid results
        updated_outputs = []
        for i, result in enumerate(results):
            if isinstance(result, Exception):
                logger.error(f"Debate  │ Agent {agents[i].agent_id} failed: {result}")
                # Keep the agent's previous output, marked as failed
                prev = output_map.get(agents[i].agent_id)
                if prev:
                    # Mark this output as a stale carry-forward (used by consensus fix D)
                    prev.failed_round = round_number
                    updated_outputs.append(prev)
            else:
                updated_outputs.append(result)
                # Publish to workspace
                await workspace.publish(
                    WorkspaceEvent(
                        event_type=EventType.CRITIQUE,
                        agent_id=result.agent_id,
                        execution_id=self.execution_id,
                        round_number=round_number,
                        data=result.to_dict(),
                    )
                )

        logger.info(
            f"Debate  │ Round {round_number} complete — {len(updated_outputs)} outputs"
        )
        return updated_outputs

    def _context_tokens_for(self, agent: BaseAgent) -> int | None:
        """Recipient model context window, or None when unknown."""
        provider_name = getattr(getattr(agent, "provider", None), "provider_name", "")
        model_id = getattr(agent, "model", "")
        if self._config is None or not provider_name or not model_id:
            return None
        try:
            context = self._config.limits_of(provider_name, model_id).context_tokens
        except (KeyError, AttributeError):
            return None
        return context if isinstance(context, int) else None

    def _per_other_chars(self, agent: BaseAgent, other_count: int) -> int | None:
        """Chars allowed per other-agent output, or None for legacy caps.

        Budget = min(recipient context, MAX_DEBATE_PROMPT_TOKENS) minus
        headroom for the answer and prompt overhead — never the team
        minimum. Unknown context falls back to the fixed caps with a
        warning (never a crash).
        """
        if other_count <= 0:
            return None
        context = self._context_tokens_for(agent)
        if context is None:
            logger.warning(
                "Debate  │ unknown context window for "
                f"{getattr(getattr(agent, 'provider', None), 'provider_name', '?')}"
                f"/{getattr(agent, 'model', '?')}; using fixed compression caps"
            )
            return None
        budget_tokens = (
            min(context, self.MAX_DEBATE_PROMPT_TOKENS)
            - self.ANSWER_RESERVE_TOKENS
            - self.PROMPT_OVERHEAD_TOKENS
        )
        if budget_tokens <= 0:
            return self.MIN_PER_OTHER_CHARS
        return max(
            self.MIN_PER_OTHER_CHARS,
            (budget_tokens * self.CHARS_PER_TOKEN) // other_count,
        )

    def _compress_outputs(
        self, outputs: list[AgentOutput], per_other_chars: int | None = None
    ) -> list[AgentOutput]:
        """
        Create compressed copies of agent outputs to reduce context window usage.

        Truncates long positions, limits evidence items, and shortens reasoning.
        With per_other_chars (from the recipient's budget) the position gets
        3/4 and the reasoning 1/4; without it the legacy fixed caps apply.
        The original outputs are NOT modified — compressed copies are returned.
        """
        position_cap = (
            self.MAX_POSITION_CHARS
            if per_other_chars is None
            else per_other_chars * 3 // 4
        )
        reasoning_cap = (
            self.MAX_REASONING_CHARS
            if per_other_chars is None
            else per_other_chars // 4
        )
        compressed = []
        for o in outputs:
            # Truncate position
            position = o.position
            if len(position) > position_cap:
                position = position[:position_cap] + "... [truncated]"

            # Limit evidence items
            evidence = o.evidence[: self.MAX_EVIDENCE_ITEMS]

            # Truncate reasoning summary
            reasoning_summary = o.reasoning_summary
            if len(reasoning_summary) > reasoning_cap:
                reasoning_summary = (
                    reasoning_summary[:reasoning_cap] + "... [truncated]"
                )

            compressed.append(
                AgentOutput(
                    agent_id=o.agent_id,
                    agent_type=o.agent_type,
                    position=position,
                    reasoning_summary=reasoning_summary,
                    confidence=o.confidence,
                    confidence_raw=o.confidence_raw,
                    evidence=evidence,
                    supports=o.supports,
                    disagrees_with=o.disagrees_with,
                    remaining_uncertainty=o.remaining_uncertainty[
                        :2
                    ],  # Cap uncertainties too
                    sources=o.sources,
                    provider=o.provider,
                    model=o.model,
                    family=o.family,
                    tokens_used=o.tokens_used,
                    latency_ms=o.latency_ms,
                    failed_round=o.failed_round,
                    raw_content="",  # Don't carry raw content into context
                )
            )
        return compressed

    async def _agent_critique(
        self,
        agent: BaseAgent,
        question: str,
        others: list[AgentOutput],
        round_number: int,
        timeout_s: float | None = None,
    ) -> AgentOutput:
        """Have a single agent critique others' work, optionally time-bounded."""
        if timeout_s is None:
            return await agent.critique(question, others, round_number)
        async with asyncio.timeout(timeout_s):
            return await agent.critique(question, others, round_number)

    @staticmethod
    async def _timed_run(
        agent: BaseAgent, question: str, timeout_s: float | None
    ) -> AgentOutput:
        """Solo re-run for single-agent teams, optionally time-bounded."""
        if timeout_s is None:
            return await agent.run(question)
        async with asyncio.timeout(timeout_s):
            return await agent.run(question)
