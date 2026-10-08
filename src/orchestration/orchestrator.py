"""
Assembly — Main Orchestrator

The central engine that manages the full execution lifecycle:
Question → Planning → Team Formation → Independent Solving →
Debate → Consensus → Synthesis → Final Answer

This is the core of Assembly (PRD Section 9.2).
"""

import asyncio
from collections.abc import Awaitable, Callable
from datetime import datetime, timezone

from src.agents.synthesizer import SynthesizerAgent
from src.core.keystore import RequestKeyStore
from src.core.logging_config import logger
from src.orchestration.agent_manager import AgentManager
from src.orchestration.budget_controller import BudgetController
from src.orchestration.capacity import (
    AGENT_CALL_SECONDS,
    PLANNER_CALL_SECONDS,
    KeyBudget,
    heuristic_suggestion,
    plan_capacity,
)
from src.orchestration.consensus import ConsensusEngine
from src.orchestration.debate import DebateManager
from src.orchestration.planner import Planner
from src.orchestration.time_controller import (
    Deadline,
    ExecState,
    InvalidStateTransition,
    StateMachine,
)
from src.orchestration.workspace import workspace
from src.providers.router import ModelRouter
from src.research.search import SearchEngine


class ExecutionResult:
    """Final result of an orchestrated execution."""

    def __init__(
        self,
        answer: str,
        sources: list,
        consensus_score: float,
        problem_type: str,
        complexity: str,
        agent_count: int,
        debate_rounds: int,
        total_tokens: int,
        providers_used: list | None = None,
        status: str = "completed",
        routing: list | None = None,
        degraded: bool = False,
        warnings: list | None = None,
    ):
        self.answer = answer
        self.sources = sources
        self.consensus_score = consensus_score
        self.problem_type = problem_type
        self.complexity = complexity
        self.agent_count = agent_count
        self.debate_rounds = debate_rounds
        self.total_tokens = total_tokens
        self.providers_used = providers_used or []
        self.status = status
        # Per-agent routing provenance (provider/model/family/reason/role).
        self.routing = routing or []
        self.degraded = degraded
        self.warnings = warnings or []


class Orchestrator:
    """
    The main orchestration engine for Assembly.

    Lifecycle:
    1. Planner classifies the problem
    2. Agent Manager forms a temporary team
    3. Agents solve independently (preventing groupthink)
    4. Debate Manager runs cross-agent debate rounds
    5. Consensus Engine evaluates agreement
    6. If consensus insufficient and time remains → more debate
    7. Synthesizer produces the final answer
    8. User receives answer + sources
    """

    def __init__(self):
        self.router = ModelRouter()
        self.search_engine = SearchEngine()
        # Live per-execution deadlines, keyed by execution id. Populated on
        # execute() entry, removed when the run settles. request_cancel()
        # flips the flag here; the API layer also cancels the task itself.
        self._deadlines: dict[str, Deadline] = {}

    def request_cancel(self, execution_id: str) -> bool:
        """Flag a running execution for user cancellation.

        Returns True when a live run was flagged. The orchestrator checks
        the flag at phase boundaries; the API layer additionally cancels
        the background task for prompt delivery.
        """
        deadline = self._deadlines.get(execution_id)
        if deadline is None:
            return False
        deadline.request_cancel()
        logger.info(f"Exec    │ Cancellation requested for {execution_id[:8]}...")
        return True

    async def execute(
        self,
        execution_id: str,
        question: str,
        time_budget_minutes: int,
        on_progress: Callable[[dict], Awaitable[None]] | None = None,
        provider_keys: dict[str, str] | None = None,
        deadline: Deadline | None = None,
    ) -> ExecutionResult:
        """
        Run the full orchestration pipeline.

        Args:
            execution_id: Unique execution identifier.
            question: User's question.
            time_budget_minutes: Time budget (3/5/10/15 minutes).
            on_progress: Async callback for real-time progress events.
            provider_keys: Per-request BYOK keys (web mode). Held in memory
                for this run only via RequestKeyStore and wiped afterwards;
                when None, the router's own (mode) key set is used.
            deadline: Wall-clock budget. Built from time_budget_minutes when
                omitted; tests inject short/fake-clock deadlines directly.

        State transitions follow docs/WORKFLOW.md section 2 and are
        validated by StateMachine (CREATED → CAPACITY_CHECK → PLANNING →
        TEAM_READY → SOLVING → EVALUATING ⇄ DEBATING → SYNTHESIZING →
        COMPLETED, with CANCELLED reachable from anywhere). A user cancel
        surfaces as asyncio.CancelledError and returns status "cancelled";
        an expired deadline instead falls through to synthesis with
        whatever positions exist.
        """
        logger.info(f"═══ EXECUTION START: {execution_id} ═══")
        logger.info(f"Question: {question[:100]}...")
        logger.info(f"Budget: {time_budget_minutes} minutes")

        # Per-request keys get an isolated in-memory store + router.
        key_store = (
            RequestKeyStore(provider_keys) if provider_keys is not None else None
        )
        router = ModelRouter(keys=key_store.get_keys()) if key_store else self.router

        # Initialize components
        budget = BudgetController(time_budget_minutes)
        if deadline is None:
            deadline = Deadline(budget_seconds=time_budget_minutes * 60)
        self._deadlines[execution_id] = deadline
        state_machine = StateMachine()
        consensus_engine = ConsensusEngine()
        planner = Planner(router)
        agent_manager = AgentManager(router, execution_id)
        debate_manager = DebateManager(execution_id)

        total_tokens = 0
        warnings: list[str] = []

        async def transition(
            state: ExecState,
            status: str | None = None,
            message: str | None = None,
        ) -> None:
            """Validate a lifecycle move and publish it as a progress event."""
            state_machine.transition(state)
            data: dict = {"state": state.value}
            if status is not None:
                data["status"] = status
            if message is not None:
                data["message"] = message
            await self._emit_progress(on_progress, execution_id, "status_update", data)

        try:
            # ════════════════════════════════════════════════════════════
            # PHASE 0: CAPACITY CHECK — What can we afford? (advisory)
            # ════════════════════════════════════════════════════════════
            await transition(
                ExecState.CAPACITY_CHECK,
                status="capacity_check",
                message="Checking available capacity...",
            )
            warnings.extend(self._advisory_capacity_check(router, question))

            # ════════════════════════════════════════════════════════════
            # PHASE 1: PLANNING — Classify the problem
            # ════════════════════════════════════════════════════════════
            await transition(
                ExecState.PLANNING,
                status="planning",
                message="Analyzing your question...",
            )

            async with asyncio.timeout(
                deadline.timeout_for_call(PLANNER_CALL_SECONDS)
            ):
                plan = await planner.plan(question, time_budget_minutes)

            await self._emit_progress(
                on_progress,
                execution_id,
                "status_update",
                {
                    "status": "planning",
                    "state": ExecState.PLANNING.value,
                    "message": f"Classified as {plan.complexity} complexity {plan.problem_type} problem",
                    "problem_type": plan.problem_type,
                    "complexity": plan.complexity,
                },
            )

            # ════════════════════════════════════════════════════════════
            # PHASE 2: TEAM FORMATION — Create agents
            # ════════════════════════════════════════════════════════════
            await self._emit_progress(
                on_progress,
                execution_id,
                "status_update",
                {
                    "status": "forming_team",
                    "state": ExecState.PLANNING.value,
                    "message": f"Assembling a team of {len(plan.team_composition)} experts...",
                },
            )

            agents = agent_manager.create_team(
                team_composition=plan.team_composition,
                problem_type=plan.problem_type,
                complexity=plan.complexity,
                time_budget_minutes=time_budget_minutes,
            )

            for agent in agents:
                budget.record_agent_created()

            state_machine.transition(ExecState.TEAM_READY)

            # Send agent info to frontend
            agent_info = agent_manager.get_agent_info()

            # Track which providers are being used
            providers_used = list(
                {a.get("provider_name", "unknown") for a in agent_info}
            )

            await self._emit_progress(
                on_progress,
                execution_id,
                "agent_update",
                {
                    "agents": agent_info,
                    "state": ExecState.TEAM_READY.value,
                    "message": "Team assembled",
                },
            )

            # ════════════════════════════════════════════════════════════
            # PHASE 3: WEB RESEARCH (if needed)
            # ════════════════════════════════════════════════════════════
            search_results = []
            if plan.needs_research and budget.can_search():
                await self._emit_progress(
                    on_progress,
                    execution_id,
                    "status_update",
                    {
                        "status": "researching",
                        "message": "Searching for evidence...",
                    },
                )

                search_results = await self.search_engine.search(question)
                budget.record_search(len(search_results))

            # ════════════════════════════════════════════════════════════
            # PHASE 4: INDEPENDENT SOLVING — Each agent works alone
            # ════════════════════════════════════════════════════════════
            await self._emit_progress(
                on_progress,
                execution_id,
                "status_update",
                {
                    "status": "solving",
                    "state": ExecState.SOLVING.value,
                    "message": "Agents solving independently...",
                    **budget.get_status(),
                },
            )

            # Inject search results for researcher agents
            for agent in agents:
                if hasattr(agent, "search_results"):
                    agent.search_results = search_results

            state_machine.transition(ExecState.SOLVING)
            deadline.raise_if_cancelled()
            outputs = await agent_manager.run_all_independent(
                agents,
                question,
                timeout_s=deadline.timeout_for_call(),
            )

            # Aggregate token usage from independent solving phase
            for o in outputs:
                total_tokens += o.tokens_used
            budget.record_tokens(sum(o.tokens_used for o in outputs))

            # ════════════════════════════════════════════════════════════
            # PHASE 5: DEBATE — Cross-agent critique rounds
            # ════════════════════════════════════════════════════════════
            round_number = 1
            adversarial_done = False
            state_machine.transition(ExecState.EVALUATING)
            consensus_result = consensus_engine.evaluate(
                outputs,
                round_number,
                time_for_round=budget.has_time_for_debate()
                and deadline.can_start_round(AGENT_CALL_SECONDS),
                # Token budget is the only quota signal the budget
                # controller owns; treat near-exhaustion as quota pressure.
                quota_ok=not budget.is_token_limited(),
            )

            await self._emit_progress(
                on_progress,
                execution_id,
                "consensus_update",
                {
                    "consensus_score": consensus_result.score,
                    "round": round_number,
                    "decision": consensus_result.decision,
                    "reasoning": consensus_result.reason,
                    "state": ExecState.EVALUATING.value,
                    **budget.get_status(),
                },
            )

            # Debate loop: DEBATE and ADVERSARIAL both mean "not done yet";
            # FINALIZE and FORCE_FINALIZE fall through to synthesis. The
            # deadline is a hard cutoff: once only the synthesis reserve
            # remains, no new round starts and current positions go to
            # synthesis as-is.
            while (
                consensus_result.decision in ("DEBATE", "ADVERSARIAL")
                and budget.can_debate()
                and not budget.should_force_synthesis()
                and not deadline.should_synthesize_now()
            ):
                # User cancellation surfaces here even between phases.
                deadline.raise_if_cancelled()
                if not deadline.can_start_round(AGENT_CALL_SECONDS):
                    logger.info(
                        f"Exec    │ {execution_id[:8]}... out of time for "
                        "another round — synthesizing from current positions"
                    )
                    break
                if consensus_result.decision == "ADVERSARIAL" and not adversarial_done:
                    adversarial_done = True
                    # The strike is a targeted round: EVALUATING → DEBATING.
                    state_machine.transition(ExecState.DEBATING)
                    challenged = await self._run_adversarial_round(
                        consensus_engine,
                        agents,
                        question,
                        outputs,
                        round_number,
                        budget,
                        on_progress,
                        execution_id,
                    )
                    if challenged is not None:
                        outputs, consensus_result, challenge_tokens = challenged
                        total_tokens += challenge_tokens
                        budget.record_tokens(challenge_tokens)
                        budget.record_debate_round()
                        state_machine.transition(ExecState.EVALUATING)
                        await self._emit_progress(
                            on_progress,
                            execution_id,
                            "consensus_update",
                            {
                                "consensus_score": consensus_result.score,
                                "round": round_number,
                                "decision": consensus_result.decision,
                                "reasoning": consensus_result.reason,
                                "state": ExecState.EVALUATING.value,
                                **budget.get_status(),
                            },
                        )
                        continue
                    # No eligible critic (or the strike failed):
                    # fall through to a normal debate round (already in
                    # DEBATING when the strike was attempted).
                if state_machine.state != ExecState.DEBATING:
                    state_machine.transition(ExecState.DEBATING)
                round_number += 1

                await self._emit_progress(
                    on_progress,
                    execution_id,
                    "status_update",
                    {
                        "status": "debating",
                        "state": ExecState.DEBATING.value,
                        "message": f"Debate round {round_number}...",
                        "round": round_number,
                        **budget.get_status(),
                    },
                )

                # Run debate round
                outputs = await debate_manager.run_debate_round(
                    agents=agents,
                    current_outputs=outputs,
                    question=question,
                    round_number=round_number,
                    timeout_s=deadline.timeout_for_call(),
                )
                budget.record_debate_round()

                # Aggregate token usage from debate round
                round_tokens = sum(o.tokens_used for o in outputs)
                total_tokens += round_tokens
                budget.record_tokens(round_tokens)

                # Re-evaluate consensus
                force = budget.should_force_synthesis()
                state_machine.transition(ExecState.EVALUATING)
                consensus_result = consensus_engine.evaluate(
                    outputs,
                    round_number,
                    force_finalize=force,
                    time_for_round=budget.has_time_for_debate()
                    and deadline.can_start_round(AGENT_CALL_SECONDS),
                    quota_ok=not budget.is_token_limited(),
                    allow_adversarial=not adversarial_done,
                )

                await self._emit_progress(
                    on_progress,
                    execution_id,
                    "consensus_update",
                    {
                        "consensus_score": consensus_result.score,
                        "round": round_number,
                        "decision": consensus_result.decision,
                        "reasoning": consensus_result.reason,
                        "state": ExecState.EVALUATING.value,
                        **budget.get_status(),
                    },
                )

            # ════════════════════════════════════════════════════════════
            # PHASE 6: FINAL SYNTHESIS — Produce the answer
            # ════════════════════════════════════════════════════════════
            deadline.raise_if_cancelled()
            state_machine.transition(ExecState.SYNTHESIZING)
            await self._emit_progress(
                on_progress,
                execution_id,
                "status_update",
                {
                    "status": "synthesizing",
                    "state": ExecState.SYNTHESIZING.value,
                    "message": "Synthesizing final answer...",
                    "consensus_score": consensus_result.score,
                    **budget.get_status(),
                },
            )

            # Create synthesizer agent
            synthesizer = agent_manager.create_agent(
                agent_type="synthesizer",
                role_description="Final Answer Synthesizer",
                problem_type=plan.problem_type,
                complexity=plan.complexity,
                time_budget_minutes=time_budget_minutes,
            )

            # Cast to SynthesizerAgent for the synthesize() method
            assert isinstance(synthesizer, SynthesizerAgent)

            # Bounded by whatever wall-clock remains (floored): synthesis
            # must finish even when the deadline already passed, because
            # there is nothing else left to produce an answer.
            async with asyncio.timeout(deadline.synthesis_timeout()):
                final_output = await synthesizer.synthesize(
                    question=question,
                    agent_outputs=outputs,
                    consensus_score=consensus_result.score,
                    debate_rounds=round_number,
                    providers_used=providers_used,
                )

            # Aggregate token usage from synthesis
            total_tokens += final_output.tokens_used
            budget.record_tokens(final_output.tokens_used)

            # ════════════════════════════════════════════════════════════
            # DONE — Return the result
            # ════════════════════════════════════════════════════════════
            sources = [s.model_dump() for s in final_output.sources]
            if not sources:
                # Collect sources from all agents
                for o in outputs:
                    sources.extend(s.model_dump() for s in o.sources)

            result = ExecutionResult(
                answer=final_output.position,
                sources=sources,
                consensus_score=consensus_result.score,
                problem_type=plan.problem_type,
                complexity=plan.complexity,
                agent_count=len(agents),
                debate_rounds=round_number,
                total_tokens=total_tokens,
                providers_used=providers_used,
                status="completed",
                routing=agent_manager.get_agent_info(),
                degraded=getattr(agent_manager.last_routing, "degraded", False),
                warnings=list(
                    getattr(agent_manager.last_routing, "warnings", []) or []
                )
                + warnings,
            )

            state_machine.transition(ExecState.COMPLETED)
            await self._emit_progress(
                on_progress,
                execution_id,
                "answer_ready",
                {
                    "status": "completed",
                    "state": ExecState.COMPLETED.value,
                    "answer": result.answer,
                    "sources": result.sources,
                    "consensus_score": result.consensus_score,
                    "agent_count": result.agent_count,
                    "providers_used": result.providers_used,
                    **budget.get_status(),
                },
            )

            logger.info(
                f"═══ EXECUTION COMPLETE: {execution_id} ═══\n"
                f"    Consensus: {consensus_result.score:.0%}\n"
                f"    Agents: {len(agents)}\n"
                f"    Debate rounds: {round_number}\n"
                f"    Time: {budget.state.elapsed_seconds:.1f}s"
            )

            # Cleanup workspace
            workspace.cleanup(execution_id)

            # Drop per-request keys: they must not outlive this run.
            if key_store is not None:
                key_store.clear()

            return result

        except asyncio.CancelledError:
            # User cancellation (API cancel endpoint or deadline flag):
            # no new work, keys wiped, state CANCELLED from anywhere.
            logger.info(f"═══ EXECUTION CANCELLED: {execution_id} ═══")
            try:
                if not state_machine.terminal:
                    state_machine.transition(ExecState.CANCELLED)
            except InvalidStateTransition as e:
                logger.warning(f"Exec    │ Cancel transition issue: {e}")
            workspace.cleanup(execution_id)
            if key_store is not None:
                key_store.clear()
            try:
                await self._emit_progress(
                    on_progress,
                    execution_id,
                    "status_update",
                    {
                        "status": "cancelled",
                        "state": ExecState.CANCELLED.value,
                        "message": "Execution cancelled by user.",
                    },
                )
            except Exception as e:  # noqa: BLE001 — best-effort final event only
                logger.debug(f"Exec    │ Cancel event unsent: {e}")
            return ExecutionResult(
                answer="",
                sources=[],
                consensus_score=0.0,
                problem_type="unknown",
                complexity="unknown",
                agent_count=0,
                debate_rounds=0,
                total_tokens=total_tokens,
                status="cancelled",
            )
        except Exception as e:  # noqa: BLE001 — execution must fail closed, never crash the worker
            # Server side keeps the full (masked) error; clients get a
            # generic message — exception text may carry provider details.
            logger.error(f"═══ EXECUTION FAILED: {execution_id} — {e} ═══")
            await self._emit_progress(
                on_progress,
                execution_id,
                "error",
                {
                    "status": "failed",
                    "message": "Execution failed; see server logs for details.",
                },
            )
            workspace.cleanup(execution_id)
            if key_store is not None:
                key_store.clear()
            return ExecutionResult(
                answer="An error occurred while processing your question. Please try again.",
                sources=[],
                consensus_score=0.0,
                problem_type="unknown",
                complexity="unknown",
                agent_count=0,
                debate_rounds=0,
                total_tokens=0,
                status="failed",
            )
        finally:
            # The run settled: drop the deadline registration so a later
            # cancel request correctly reports "unknown run".
            self._deadlines.pop(execution_id, None)

    @staticmethod
    def _advisory_capacity_check(router, question: str) -> list[str]:
        """WORKFLOW section 4 review: what can this run afford?

        Advisory only — findings become warnings on the result, never a
        veto. Anything failing here degrades to silence, never to a crash:
        the planner and consensus still do their jobs.
        """
        snapshot = getattr(router, "quota_snapshot", None)
        if not callable(snapshot):
            return []
        try:
            keys = [
                KeyBudget(
                    provider=entry.get("provider", "unknown"),
                    rpm_limit=entry.get("rpm_limit"),
                    rpd_remaining=entry.get("rpd_remaining"),
                )
                for entry in snapshot()
            ]
            suggestion = heuristic_suggestion(question)
            # Tier is unknown before planning; use the largest tier so the
            # review reflects total affordable capacity, not a tier cap.
            verdict = plan_capacity(keys, 15, suggestion)
            logger.info(
                f"Capacity │ Advisory check: {verdict.explanation} "
                f"(affordable={verdict.affordable_calls})"
            )
            return list(verdict.warnings)
        except Exception as e:  # noqa: BLE001 — advisory only, never break the run
            logger.warning(f"Capacity │ Advisory check skipped: {e}")
            return []

    async def _run_adversarial_round(
        self,
        consensus_engine,
        agents,
        question: str,
        outputs,
        round_number: int,
        budget,
        on_progress,
        execution_id: str,
    ):
        """One WORKFLOW 5b strike: a different-family critic attacks the consensus.

        Returns (outputs, report, challenge_tokens), or None when there is
        no eligible critic or the strike itself fails — the caller then runs
        a normal debate round instead.
        """
        from src.orchestration.consensus import ConsensusEngine

        critics = [a for a in agents if a.agent_type == "critic"]
        critic = ConsensusEngine.select_adversarial_critic(critics, outputs)
        if critic is None:
            logger.info(
                "Orchestrator │ No different-family critic for adversarial "
                "round — debating normally"
            )
            return None

        await self._emit_progress(
            on_progress,
            execution_id,
            "status_update",
            {
                "status": "adversarial",
                "state": ExecState.DEBATING.value,
                "message": f"Adversarial challenge by {critic.agent_id} "
                f"({critic.family}) — assuming the consensus is wrong...",
                "round": round_number,
                **budget.get_status(),
            },
        )
        try:
            new_outputs, report = await consensus_engine.adversarial_round(
                critic,
                question,
                outputs,
                round_number,
                time_for_round=budget.has_time_for_debate(),
                quota_ok=not budget.is_token_limited(),
            )
        except Exception as e:  # noqa: BLE001 — a failed strike must not kill the run
            logger.error(f"Orchestrator │ Adversarial round failed: {e}")
            return None
        challenge = next(
            (o for o in new_outputs if o.agent_id == critic.agent_id), None
        )
        return new_outputs, report, challenge.tokens_used if challenge else 0

    async def _emit_progress(
        self,
        callback: Callable[[dict], Awaitable[None]] | None,
        execution_id: str,
        event_type: str,
        data: dict,
    ):
        """Send a progress event to the frontend via callback."""
        if callback:
            try:
                await callback(
                    {
                        "event_type": event_type,
                        "execution_id": execution_id,
                        "data": data,
                        "timestamp": datetime.now(timezone.utc).isoformat(),
                    }
                )
            except Exception as e:  # noqa: BLE001 — a broken callback must not kill the run
                logger.error(f"Orchestrator │ Progress callback error: {e}")
