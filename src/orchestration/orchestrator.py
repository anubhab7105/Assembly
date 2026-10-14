"""
Assembly — Main Orchestrator

The central engine that manages the full execution lifecycle:
Question → Planning → Team Formation → Independent Solving →
Debate → Consensus → Synthesis → Final Answer

This is the core of Assembly (PRD Section 9.2).
"""

import asyncio
from collections.abc import Awaitable, Callable
from urllib.parse import urlsplit

from src.agents.synthesizer import SynthesizerAgent
from src.api.events import (
    EventRecorder,
    ProgressEventType,
    confidence_label,
    diff_disagreements,
)
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
from src.orchestration.circuit_breaker import cross_run_health
from src.orchestration.composer import compose_final_answer
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
from src.providers.router import (
    ModelRouter,
    PinViolationError,
    normalize_allowed_families,
)
from src.research.crawler import crawl_search_results, normalize_search_results
from src.research.router import SearchRouter, default_providers
from src.research.sanitize import sanitize_search_results, summarize_flags


def cap_label_for_degraded(label: str, degraded: bool) -> str:
    """One band down when the team had a single family (WORKFLOW).

    DEGRADED teams cannot claim High confidence: High becomes Moderate.
    """
    if degraded and label == "High":
        return "Moderate"
    return label


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
        verification: dict | None = None,
        call_log: list | None = None,
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
        # Verification summary from the final composer (agents, families,
        # rounds, disagreements resolved, sources verified).
        self.verification = verification or {}
        # Per-LLM-call token log for measurement (stage, role,
        # provider/model/family, input/output/reasoning/total). Names and
        # counts only — never keys or prompt content.
        self.call_log = call_log or []


def _research_degraded(agents: list, call_log: list[dict]) -> bool:
    """True when the team has a researcher but none answered successfully.

    A successful researcher call is a solve/debate/adversarial log entry
    with role "researcher" and total_tokens > 0 (failed calls log 0).
    Pure helper: easy to unit-test without running an execution.
    """
    if not any(getattr(a, "agent_type", "") == "researcher" for a in agents):
        return False
    for entry in call_log or []:
        if not isinstance(entry, dict):
            continue
        if entry.get("role") != "researcher":
            continue
        if entry.get("stage") not in ("solve", "debate", "adversarial"):
            continue
        try:
            total = int(entry.get("total_tokens", 0) or 0)
        except (TypeError, ValueError):
            total = 0
        if total > 0:
            return False
    return True


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
        # Search is built per execution (per-request keys + keyless
        # fallback); no shared search state across runs.
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
        search_keys: dict[str, str] | None = None,
        deadline: Deadline | None = None,
        router_override=None,
        allowed_families: list[str] | None = None,
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
            search_keys: Per-request search keys (e.g. {"tavily": ...}).
                In memory only for this run; without a Tavily key the
                research router uses keyless providers. Never logged.
            deadline: Wall-clock budget. Built from time_budget_minutes when
                omitted; tests inject short/fake-clock deadlines directly.
            router_override: Optional router instance to use instead of the default.
                Used for injecting ReplayRouter during demo mode.
            allowed_families: Bench family pins — planner, team, and
                synthesizer stay inside these families. A role with no
                pinned candidate raises PinViolationError (loud) instead
                of substituting silently; the planner instead falls back
                to its zero-call heuristic. None = unconstrained.

        State transitions follow docs/WORKFLOW.md section 2 and are
        validated by StateMachine (CREATED → CAPACITY_CHECK → PLANNING →
        TEAM_READY → SOLVING → EVALUATING ⇄ DEBATING → SYNTHESIZING →
        COMPLETED, with CANCELLED reachable from anywhere). A user cancel
        surfaces as asyncio.CancelledError and returns status "cancelled";
        an expired deadline instead falls through to synthesis with
        whatever positions exist.
        """
        logger.info(f"═══ EXECUTION START: {execution_id} ═══")
        logger.info(f"Question chars: {len(question)}")
        logger.info(f"Budget: {time_budget_minutes} minutes")
        if allowed_families is not None:
            allowed_families = normalize_allowed_families(allowed_families)
            logger.info(f"Pins    │ family pins: {', '.join(allowed_families or [])}")

        # Per-request keys get an isolated in-memory store + router.
        key_store = (
            RequestKeyStore(provider_keys) if provider_keys is not None else None
        )
        if router_override is not None:
            router = router_override
        else:
            router = (
                ModelRouter(keys=key_store.get_keys()) if key_store else self.router
            )

        # Per-request search keys for this run only (names never logged).
        # Without a Tavily key the router still serves keyless providers.
        # A present-but-empty field means "no search key"; an absent field
        # keeps the legacy server-key behavior where allowed.
        if search_keys is None:
            tavily_key = None
        else:
            tavily_key = (search_keys or {}).get("tavily", "")
        search_router = SearchRouter(providers=default_providers(tavily_key=tavily_key))

        # Initialize components
        budget = BudgetController(time_budget_minutes)
        if deadline is None:
            deadline = Deadline(budget_seconds=time_budget_minutes * 60)
        self._deadlines[execution_id] = deadline
        state_machine = StateMachine()
        consensus_engine = ConsensusEngine()
        planner = Planner(router)
        agent_manager = AgentManager(router, execution_id)
        debate_manager = DebateManager(execution_id, getattr(router, "config", None))

        total_tokens = 0
        warnings: list[str] = []
        call_log: list[dict] = []
        recorder = EventRecorder(execution_id)
        open_disagreement_keys: dict = {}
        disagreements_resolved = 0
        quota_warned = False

        def _record_call(
            stage: str,
            role: str,
            agent_id: str,
            provider: str,
            model: str,
            family: str,
            input_tokens: int,
            output_tokens: int,
            reasoning_tokens: int,
            total: int,
            round_no: int = 0,
        ) -> None:
            """Append one LLM-call record (names + counts only, never keys)."""
            entry = {
                "stage": stage,
                "round": round_no,
                "role": role,
                "agent_id": agent_id,
                "provider": provider or "unknown",
                "model": model or "unknown",
                "family": family or "unknown",
                "input_tokens": int(input_tokens or 0),
                "output_tokens": int(output_tokens or 0),
                "reasoning_tokens": int(reasoning_tokens or 0),
                "total_tokens": int(total or 0),
            }
            call_log.append(entry)
            logger.info(
                f"Tokens  │ {stage} r{round_no} {role} {agent_id} "
                f"{entry['provider']}/{entry['model']} "
                f"in={entry['input_tokens']} out={entry['output_tokens']} "
                f"reason={entry['reasoning_tokens']} total={entry['total_tokens']}"
            )

        async def emit_event(
            event_type: ProgressEventType | str,
            payload: dict,
        ) -> dict | None:
            """Validate + sequence one §8 event, then forward it.

            The current lifecycle state rides in the envelope so the API
            can persist live phases. A contract violation here is an
            orchestrator bug, never a reason to kill the run: log it
            loudly (tests assert zero drops on mock runs) and continue
            without the event.
            """
            try:
                event = recorder.emit(
                    event_type, payload, state=state_machine.state.value
                )
            except Exception as e:  # noqa: BLE001 — observability must not break runs
                logger.error(f"Exec    │ Dropping invalid progress event: {e}")
                return None
            await self._send_event(on_progress, event)
            return event

        async def transition(
            state: ExecState,
            event_type: ProgressEventType | str,
            payload: dict,
        ) -> dict | None:
            """Validate a lifecycle move and publish it as a progress event."""
            state_machine.transition(state)
            return await emit_event(event_type, payload)

        async def emit_consensus(report, round_number: int) -> None:
            """consensus.updated + timer.tick + disagreement deltas, in order."""
            nonlocal open_disagreement_keys, quota_warned, disagreements_resolved
            await emit_event(
                ProgressEventType.CONSENSUS_UPDATED,
                {
                    "score": report.score,
                    "new_info_rate": report.new_info_rate,
                    "decision": report.decision,
                    "reason": report.reason,
                    "round": round_number,
                },
            )
            await emit_event(
                ProgressEventType.TIMER_TICK,
                {"seconds_remaining": budget.state.remaining_seconds},
            )
            deltas, open_disagreement_keys = diff_disagreements(
                open_disagreement_keys, report.open_disagreements, round_number
            )
            for event_type, payload in deltas:
                await emit_event(event_type, payload)
                if event_type == ProgressEventType.DISAGREEMENT_RESOLVED:
                    disagreements_resolved += 1
            if budget.is_token_limited() and not quota_warned:
                quota_warned = True
                await emit_event(
                    ProgressEventType.QUOTA_WARNING,
                    {
                        "provider": "token-budget",
                        "remaining": float(
                            max(0, budget.state.max_tokens - budget.state.tokens_used)
                        ),
                        "detail": "Execution token budget nearly exhausted.",
                    },
                )

        breaker_trips_seen = 0

        async def emit_breaker_trips() -> None:
            """agent.status events for newly tripped (model, role) pairs.

            The circuit breaker itself only counts; surfacing each trip as
            a visible progress event keeps reroutes auditable in the UI
            and the event log (no new event types: trips ride agent.status).
            """
            nonlocal breaker_trips_seen
            trips = agent_manager.breaker.trips[breaker_trips_seen:]
            breaker_trips_seen = len(agent_manager.breaker.trips)
            for trip in trips:
                await emit_event(
                    ProgressEventType.AGENT_STATUS,
                    {
                        "role": str(trip.get("role", "")),
                        "activity": (
                            f"Circuit breaker OPEN for {trip.get('model')} on "
                            f"{trip.get('role')} after {trip.get('failures')} "
                            "failures; further calls rerouted to a healthy model."
                        )[:500],
                        "state": state_machine.state.value,
                    },
                )

        try:
            await emit_event(
                ProgressEventType.EXECUTION_STARTED,
                {
                    "tier_minutes": time_budget_minutes,
                    "deadline_seconds": float(deadline.budget_seconds),
                },
            )
            # ════════════════════════════════════════════════════════════
            # PHASE 0: CAPACITY CHECK — What can we afford? (advisory)
            # ════════════════════════════════════════════════════════════
            await transition(
                ExecState.CAPACITY_CHECK,
                ProgressEventType.AGENT_STATUS,
                {
                    "role": "system",
                    "activity": "Checking available capacity...",
                    "state": ExecState.CAPACITY_CHECK.value,
                },
            )
            warning_texts, quota_payload = self._advisory_capacity_check(
                router, question
            )
            warnings.extend(warning_texts)
            if quota_payload is not None:
                await emit_event(ProgressEventType.QUOTA_WARNING, quota_payload)

            # ════════════════════════════════════════════════════════════
            # PHASE 1: PLANNING — Classify the problem
            # ════════════════════════════════════════════════════════════
            await transition(
                ExecState.PLANNING,
                ProgressEventType.AGENT_STATUS,
                {
                    "role": "planner",
                    "activity": "Analyzing your question...",
                    "state": ExecState.PLANNING.value,
                },
            )

            try:
                async with asyncio.timeout(
                    deadline.timeout_for_call(PLANNER_CALL_SECONDS)
                ):
                    plan = await planner.plan(
                        question, time_budget_minutes, allowed_families=allowed_families
                    )
            except TimeoutError:
                # The planner LLM call hung past its bound. asyncio delivers
                # the expiry as cancellation, which escapes plan()'s
                # never-raises contract (it only catches Exception, and
                # CancelledError must keep propagating for user cancels) —
                # so fall back to the zero-call heuristic here instead of
                # failing the run. A user cancel still surfaces as
                # CancelledError and is unaffected.
                logger.warning(
                    "Planner │ Classification timed out; using zero-call "
                    "heuristic plan"
                )
                plan = planner.heuristic_plan(
                    question,
                    time_budget_minutes,
                    "planner call timed out",
                )
                plan.capacity = planner.read_capacity(time_budget_minutes)

            if plan.planner_provider or plan.planner_total_tokens:
                _record_call(
                    "planner",
                    "planner",
                    "planner",
                    plan.planner_provider,
                    plan.planner_model,
                    plan.planner_family,
                    plan.planner_input_tokens,
                    plan.planner_output_tokens,
                    plan.planner_reasoning_tokens,
                    plan.planner_total_tokens,
                    0,
                )
                # The planner is a real LLM call against quota: count it in
                # the execution total and the token budget (previously it
                # was logged but excluded, undercounting ~400 tokens/run).
                total_tokens += plan.planner_total_tokens
                budget.record_tokens(plan.planner_total_tokens)

            await emit_event(
                ProgressEventType.PLAN_READY,
                {
                    "problem_type": plan.problem_type,
                    "complexity": plan.complexity,
                    "agent_count": len(plan.team_composition),
                },
            )
            # FR-2: surface solver/critic adds or tight-cap drops.
            plan_adjustments = list(getattr(plan, "plan_adjustments", []) or [])
            if plan_adjustments:
                from src.orchestration.core_roles import final_roles_with_synthesizer

                await emit_event(
                    ProgressEventType.PLAN_ADJUSTED,
                    {
                        "reason": "; ".join(plan_adjustments)[:500],
                        "added": [a for a in plan_adjustments if a.startswith("added")],
                        "removed": [
                            a for a in plan_adjustments if a.startswith("dropped")
                        ],
                        "final_roles": final_roles_with_synthesizer(
                            list(getattr(plan, "suggested_roles", []) or [])
                        ),
                    },
                )

            # ════════════════════════════════════════════════════════════
            # PHASE 2: TEAM FORMATION — Create agents
            # ════════════════════════════════════════════════════════════
            await emit_event(
                ProgressEventType.AGENT_STATUS,
                {
                    "role": "",
                    "activity": f"Assembling a team of {len(plan.team_composition)} experts...",
                    "state": ExecState.PLANNING.value,
                },
            )

            agents = agent_manager.create_team(
                team_composition=plan.team_composition,
                problem_type=plan.problem_type,
                complexity=plan.complexity,
                time_budget_minutes=time_budget_minutes,
                allowed_families=allowed_families,
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

            await emit_event(
                ProgressEventType.TEAM_READY,
                {
                    "roles": [
                        {
                            "agent_id": entry.get("agent_id", ""),
                            "agent_type": entry.get("agent_type", ""),
                            "model": entry.get("model", ""),
                            "provider_name": entry.get("provider_name", ""),
                            "role_description": entry.get("role_description", ""),
                            "family": entry.get("family", ""),
                        }
                        for entry in agent_info
                    ],
                },
            )
            # FR-2: single-family teams cannot give the critic a different
            # family; warn in the run and lower confidence downstream.
            try:
                from src.orchestration.core_roles import single_family_warning

                team_families = [str(e.get("family", "") or "") for e in agent_info]
                fam_warning = single_family_warning(team_families)
                if fam_warning:
                    warnings.append(fam_warning)
                    plan.reasoning = (plan.reasoning + " " + fam_warning).strip()
                    await emit_event(
                        ProgressEventType.PLAN_ADJUSTED,
                        {
                            "reason": fam_warning[:500],
                            "added": [],
                            "removed": [],
                            "final_roles": sorted(
                                {str(e.get("agent_type", "")) for e in agent_info}
                                | {"synthesizer"}
                            ),
                        },
                    )
            except Exception:  # noqa: BLE001 — warning must not break the run
                pass

            # ════════════════════════════════════════════════════════════
            # PHASE 3: WEB RESEARCH (if needed)
            # ════════════════════════════════════════════════════════════
            search_results = []
            if plan.needs_research and budget.can_search():
                await emit_event(
                    ProgressEventType.AGENT_STATUS,
                    {
                        "role": "researcher",
                        "activity": "Searching for evidence...",
                        "state": ExecState.TEAM_READY.value,
                    },
                )

                raw_search_results = await search_router.search(
                    question, problem_type=getattr(plan, "problem_type", "general")
                )
                budget.record_search(len(raw_search_results))
                used_sources = search_router.last_providers_used

                # Crawl static HTML opportunistically within the execution
                # deadline. Searching remains useful when a page is blocked,
                # non-HTML, unsafe, or too slow to fetch.
                crawl_seconds = min(8.0, max(0.0, deadline.remaining() - 25.0))
                if raw_search_results and crawl_seconds > 0:
                    await emit_event(
                        ProgressEventType.AGENT_STATUS,
                        {
                            "role": "researcher",
                            "activity": "Reading permitted source pages (bounded static crawl)...",
                            "state": ExecState.TEAM_READY.value,
                        },
                    )
                    search_results = await crawl_search_results(
                        raw_search_results,
                        total_timeout_seconds=crawl_seconds,
                    )
                else:
                    search_results = normalize_search_results(raw_search_results)
                if search_results and used_sources:
                    await emit_event(
                        ProgressEventType.AGENT_STATUS,
                        {
                            "role": "researcher",
                            "activity": f"Web search via {', '.join(used_sources)}."[:500],
                            "state": ExecState.TEAM_READY.value,
                        },
                    )
                elif not search_results:
                    await emit_event(
                        ProgressEventType.AGENT_STATUS,
                        {
                            "role": "researcher",
                            "activity": (
                                "Web search returned nothing; "
                                "no external sources were used."
                            ),
                            "state": ExecState.TEAM_READY.value,
                        },
                    )
                scan = sanitize_search_results(search_results)
                if scan.flags:
                    logger.warning(
                        f"Exec    │ Web search tripwire: {summarize_flags(scan.flags)}"
                    )
                    await emit_event(
                        ProgressEventType.AGENT_STATUS,
                        {
                            "role": "researcher",
                            "activity": (
                                f"Flagged {len(scan.flags)} suspicious web "
                                f"snippet(s) ({summarize_flags(scan.flags)}) — "
                                "sanitized before use."
                            )[:500],
                            "state": ExecState.TEAM_READY.value,
                        },
                    )
                for hit in search_results:
                    url = str(hit.get("url", ""))
                    await emit_event(
                        ProgressEventType.SOURCE_FOUND,
                        {
                            "title": str(hit.get("title", "Untitled"))[:200],
                            "domain": urlsplit(url).netloc,
                            "url": url,
                        },
                    )

            # ════════════════════════════════════════════════════════════
            # PHASE 4: INDEPENDENT SOLVING — Each agent works alone
            # ════════════════════════════════════════════════════════════
            state_machine.transition(ExecState.SOLVING)
            await emit_event(
                ProgressEventType.AGENT_STATUS,
                {
                    "role": "",
                    "activity": "Agents solving independently...",
                    "state": ExecState.SOLVING.value,
                },
            )

            # Inject search results for researcher agents
            for agent in agents:
                if hasattr(agent, "search_results"):
                    agent.search_results = search_results

            deadline.raise_if_cancelled()
            outputs = await agent_manager.run_all_independent(
                agents,
                question,
                timeout_s=deadline.timeout_for_call(),
            )

            # Aggregate token usage from independent solving phase
            for o in outputs:
                total_tokens += o.tokens_used
                _record_call(
                    "solve",
                    o.agent_type or "solver",
                    o.agent_id,
                    o.provider,
                    o.model,
                    o.family,
                    o.input_tokens,
                    o.output_tokens,
                    o.reasoning_tokens,
                    o.tokens_used,
                    1,
                )
            budget.record_tokens(sum(o.tokens_used for o in outputs))
            # Solve-phase transport failures were already counted by the
            # manager retry path; surface any trips they caused.
            await emit_breaker_trips()

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

            await emit_consensus(consensus_result, round_number)

            # FR-5: stagnation guard — never launch another plain debate after
            # a stagnant round; failed-agent rounds never count as no-change.
            from src.orchestration.stagnation import (
                compute_round_delta,
                needs_debate,
                stagnation_note,
            )

            stagnant_seen = False
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
                # FR-5: after a stagnant round, never launch another plain
                # debate — adversarial once, else force-finalize with note.
                if stagnant_seen and consensus_result.decision == "DEBATE":
                    note = stagnation_note()
                    if note not in warnings:
                        warnings.append(note)
                    logger.info(
                        "Exec    │ debate stagnated — forcing final synthesis"
                    )
                    break
                # FR-5: plain debate needs an open disagreement or thin
                # evidence; otherwise skip (no extra LLM calls spent).
                if consensus_result.decision == "DEBATE" and not needs_debate(
                    consensus_result
                ):
                    logger.info(
                        "Exec    │ no open disagreement or missing evidence — "
                        "skipping further debate"
                    )
                    break
                if (
                    consensus_result.decision == "ADVERSARIAL"
                    or (stagnant_seen and not adversarial_done)
                ) and not adversarial_done:
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
                        emit_event,
                        agent_manager,
                    )
                    await emit_breaker_trips()
                    if challenged is not None:
                        outputs, consensus_result, challenge = challenged
                        if challenge is not None:
                            total_tokens += challenge.tokens_used
                            budget.record_tokens(challenge.tokens_used)
                            _record_call(
                                "adversarial",
                                challenge.agent_type or "critic",
                                challenge.agent_id,
                                challenge.provider,
                                challenge.model,
                                challenge.family,
                                challenge.input_tokens,
                                challenge.output_tokens,
                                challenge.reasoning_tokens,
                                challenge.tokens_used,
                                round_number,
                            )
                        budget.record_debate_round()
                        state_machine.transition(ExecState.EVALUATING)
                        await emit_consensus(consensus_result, round_number)
                        continue
                    # No eligible critic (or the strike failed):
                    # fall through to a normal debate round (already in
                    # DEBATING when the strike was attempted).
                if state_machine.state != ExecState.DEBATING:
                    state_machine.transition(ExecState.DEBATING)
                round_number += 1

                await emit_event(
                    ProgressEventType.ROUND_STARTED,
                    {"round": round_number, "goal": f"Debate round {round_number}"},
                )

                # Circuit breaker: agents whose (model, role) tripped are
                # swapped onto a healthy model before the round (same
                # agent_id, so supports/disagrees_with refs keep working).
                for idx, agent in enumerate(list(agents)):
                    if agent_manager.should_avoid(agent.model, agent.agent_type):
                        label = agent_manager.reroute_open_circuit(agent)
                        if label is not None:
                            agents[idx] = agent_manager.agents[agent.agent_id]
                            providers_used = sorted(
                                {
                                    a.provider.provider_name
                                    for a in agent_manager.agents.values()
                                }
                            )
                            await emit_event(
                                ProgressEventType.AGENT_STATUS,
                                {
                                    "role": agent.agent_type,
                                    "activity": (
                                        f"Circuit breaker rerouted {agent.agent_id} "
                                        f"({agent.agent_type}) to {label} after "
                                        "repeated failures."
                                    )[:500],
                                    "state": state_machine.state.value,
                                },
                            )
                        else:
                            logger.warning(
                                f"Exec    │ {agent.agent_id} circuit-open but no "
                                "healthy fallback; keeping original model"
                            )

                # Run debate round
                prev_outputs = list(outputs)
                prev_contradiction = float(
                    (consensus_result.factors or {}).get("contradiction_ratio", 0.0)
                    or 0.0
                )
                outputs = await debate_manager.run_debate_round(
                    agents=agents,
                    current_outputs=outputs,
                    question=question,
                    round_number=round_number,
                    timeout_s=deadline.timeout_for_call(),
                )
                budget.record_debate_round()

                # Debate critiques bypass the manager retry path, so record
                # this round's transport failures here (carry-forwards with
                # failed_round == round_number) for the breaker, per-run
                # and cross-run alike.
                agents_by_id = {a.agent_id: a for a in agents}
                for o in outputs:
                    if o.failed_round == round_number:
                        failed_agent = agents_by_id.get(o.agent_id)
                        if failed_agent is not None:
                            agent_manager.breaker.record_failure(
                                failed_agent.model, failed_agent.agent_type
                            )
                            cross_run_health().record_failure(
                                failed_agent.model, failed_agent.agent_type
                            )
                await emit_breaker_trips()

                # Aggregate token usage from debate round (fresh calls only;
                # carry-forwards with failed_round == round_number reuse stale
                # output and must not double-count tokens).
                fresh = [
                    o for o in outputs if o.failed_round != round_number
                ]
                round_tokens = sum(o.tokens_used for o in fresh)
                total_tokens += round_tokens
                budget.record_tokens(round_tokens)
                for o in fresh:
                    _record_call(
                        "debate",
                        o.agent_type or "solver",
                        o.agent_id,
                        o.provider,
                        o.model,
                        o.family,
                        o.input_tokens,
                        o.output_tokens,
                        o.reasoning_tokens,
                        o.tokens_used,
                        round_number,
                    )

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

                await emit_event(
                    ProgressEventType.ROUND_FINISHED,
                    {
                        "round": round_number,
                        "outcome": f"Round {round_number} complete: "
                        f"{consensus_result.decision}",
                    },
                )
                await emit_consensus(consensus_result, round_number)
                # FR-5: stagnant rounds emit round.stagnated (no extra LLM).
                try:
                    curr_contradiction = float(
                        (consensus_result.factors or {}).get(
                            "contradiction_ratio", 0.0
                        )
                        or 0.0
                    )
                except (TypeError, ValueError):
                    curr_contradiction = 0.0
                delta = compute_round_delta(
                    prev_outputs,
                    outputs,
                    prev_contradiction,
                    curr_contradiction,
                    consensus_result.new_info_rate,
                    round_number,
                )
                if delta.stagnant:
                    stagnant_seen = True
                    await emit_event(
                        ProgressEventType.ROUND_STAGNATED,
                        {
                            "round": round_number,
                            "reason": delta.reason[:500],
                            "delta": delta.to_dict(),
                        },
                    )
                    if adversarial_done:
                        note = stagnation_note()
                        if note not in warnings:
                            warnings.append(note)
                        logger.info(
                            "Exec    │ debate stagnated after adversarial — "
                            "forcing final synthesis"
                        )
                        break

            # ════════════════════════════════════════════════════════════
            # PHASE 6: FINAL SYNTHESIS — Produce the answer
            # ════════════════════════════════════════════════════════════
            deadline.raise_if_cancelled()
            state_machine.transition(ExecState.SYNTHESIZING)
            await emit_event(ProgressEventType.SYNTHESIS_STARTED, {})

            # Create synthesizer agent
            synthesizer = agent_manager.create_agent(
                agent_type="synthesizer",
                role_description="Final Answer Synthesizer",
                problem_type=plan.problem_type,
                complexity=plan.complexity,
                time_budget_minutes=time_budget_minutes,
                allowed_families=allowed_families,
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
            _record_call(
                "synthesis",
                final_output.agent_type or "synthesizer",
                final_output.agent_id,
                final_output.provider,
                final_output.model,
                final_output.family,
                final_output.input_tokens,
                final_output.output_tokens,
                final_output.reasoning_tokens,
                final_output.tokens_used,
                round_number,
            )

            # ════════════════════════════════════════════════════════════
            # DONE — Compose the final answer and return the result
            # ════════════════════════════════════════════════════════════
            candidate_sources = list(final_output.sources)
            if not candidate_sources:
                # Collect sources from all agents
                for o in outputs:
                    candidate_sources.extend(o.sources)

            composed = compose_final_answer(
                agent_outputs=outputs,
                consensus_score=consensus_result.score,
                open_disagreements=consensus_result.open_disagreements,
                sources_pool=candidate_sources,
                debate_rounds=round_number,
                disagreements_resolved=disagreements_resolved,
                agent_count=len(agents),
                providers_used=providers_used,
                synth_position=final_output.position,
                synth_uncertainty=list(final_output.remaining_uncertainty),
                synth_evidence=list(final_output.evidence),
                research_degraded=_research_degraded(agents, call_log),
                research_failures=agent_manager.breaker.failures_for_role("researcher"),
                circuit_breaker_trips=[
                    f"{trip.get('model')} on {trip.get('role')}"
                    for trip in agent_manager.breaker.trips
                ],
            )
            warnings.extend(composed.warnings)
            sources = [s.model_dump() for s in composed.sources]

            result = ExecutionResult(
                answer=composed.answer_markdown,
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
                warnings=list(getattr(agent_manager.last_routing, "warnings", []) or [])
                + warnings,
                verification=composed.verification.to_dict(),
                call_log=list(call_log),
            )

            state_machine.transition(ExecState.COMPLETED)
            for source in sources:
                url = str(source.get("url", ""))
                await emit_event(
                    ProgressEventType.SOURCE_VERIFIED,
                    {
                        "title": str(source.get("title", "Untitled"))[:200],
                        "domain": urlsplit(url).netloc,
                        "url": url,
                    },
                )
            # DEGRADED (single-family) teams cannot claim High confidence:
            # one band down per WORKFLOW, with an explicit warning.
            raw_label = confidence_label(consensus_result.score)
            completed_label = cap_label_for_degraded(raw_label, bool(result.degraded))
            if raw_label == "High" and completed_label == "Moderate":
                result.warnings.append(
                    "Single model family: no independent verification; "
                    "confidence reduced from High to Moderate."
                )
            await emit_event(
                ProgressEventType.EXECUTION_COMPLETED,
                {
                    "status": "completed",
                    "answer": result.answer,
                    "sources": [
                        {
                            "title": str(source.get("title", ""))[:200],
                            "url": str(source.get("url", "")),
                            "snippet": str(source.get("snippet", ""))[:500],
                        }
                        for source in sources
                    ],
                    "confidence_label": completed_label,
                    "consensus_score": result.consensus_score,
                    "agent_count": result.agent_count,
                    "providers_used": result.providers_used,
                    "tokens_used": total_tokens,
                    "debate_rounds": round_number,
                    "elapsed_seconds": round(budget.state.elapsed_seconds, 1),
                    "verification": result.verification,
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

        except PinViolationError:
            # Bench family pins cannot serve a role: clean up exactly like
            # the failure path (workspace + per-request keys) but re-raise
            # so the bench records a PinViolation instead of a generic
            # failure. Unreachable in production (pins are bench-only).
            logger.error(f"═══ EXECUTION PIN-VIOLATION: {execution_id} ═══")
            workspace.cleanup(execution_id)
            if key_store is not None:
                key_store.clear()
            raise
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
                await emit_event(
                    ProgressEventType.EXECUTION_CANCELLED,
                    {
                        "status": "cancelled",
                        "reason": "Execution cancelled by user.",
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
                call_log=list(call_log) if "call_log" in locals() else [],
            )
        except Exception as e:  # noqa: BLE001 — execution must fail closed, never crash the worker
            # Server side keeps the full (masked) error; clients get a
            # generic message — exception text may carry provider details.
            logger.error(f"═══ EXECUTION FAILED: {execution_id} — {e} ═══")
            await emit_event(
                ProgressEventType.EXECUTION_FAILED_PARTIAL,
                {
                    "status": "failed",
                    "reason": "Execution failed; see server logs for details.",
                    "answer": "",
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
                call_log=list(call_log) if "call_log" in locals() else [],
            )
        finally:
            # The run settled: drop the deadline registration so a later
            # cancel request correctly reports "unknown run".
            self._deadlines.pop(execution_id, None)

    @staticmethod
    def _advisory_capacity_check(
        router, question: str
    ) -> tuple[list[str], dict | None]:
        """WORKFLOW section 4 review: what can this run afford?

        Advisory only — findings become warnings on the result, never a
        veto. Anything failing here degrades to silence, never to a crash:
        the planner and consensus still do their jobs.

        Returns (warnings, quota payload or None): a quota.warning event
        goes out only when the verdict actually downgrades the tier or
        finds nothing affordable.
        """
        snapshot = getattr(router, "quota_snapshot", None)
        if not callable(snapshot):
            return [], None
        try:
            keys = [
                KeyBudget(
                    provider=entry.get("provider", "unknown"),
                    rpm_limit=entry.get("rpm_limit"),
                    rpd_remaining=entry.get("rpd_remaining"),
                    tpm_limit=entry.get("tpm_limit"),
                    tpd_remaining=entry.get("tpd_remaining"),
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
            quota_payload = None
            if verdict.affordable_calls is not None and (
                verdict.downgraded or not verdict.feasible
            ):
                quota_payload = {
                    "provider": "aggregate",
                    "remaining": float(verdict.affordable_calls),
                    "detail": verdict.explanation[:200],
                }
            return list(verdict.warnings), quota_payload
        except Exception as e:  # noqa: BLE001 — advisory only, never break the run
            logger.warning(f"Capacity │ Advisory check skipped: {e}")
            return [], None

    async def _run_adversarial_round(
        self,
        consensus_engine,
        agents,
        question: str,
        outputs,
        round_number: int,
        budget,
        emit_event,
        agent_manager=None,
    ):
        """One WORKFLOW 5b strike: a different-family critic attacks the consensus.

        Returns (outputs, report, challenge_output), or None when there is
        no eligible critic or the strike itself fails — the caller then runs
        a normal debate round instead. ``emit_event`` is the recorder-backed
        emitter so the strike announcement keeps the run's dense sequence.
        challenge_output is the critic's fresh AgentOutput (with per-call
        input/output/reasoning tokens) or None.
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

        await emit_event(
            ProgressEventType.ROUND_STARTED,
            {
                "round": round_number,
                "goal": f"Adversarial challenge by {critic.agent_id} — "
                "assuming the consensus is wrong",
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
            if agent_manager is not None:
                from src.orchestration.agent_manager import RETRYABLE_ERRORS
                from src.orchestration.circuit_breaker import cross_run_health

                if isinstance(e, RETRYABLE_ERRORS):
                    agent_manager.breaker.record_failure(
                        critic.model, critic.agent_type
                    )
                    cross_run_health().record_failure(
                        critic.model, critic.agent_type
                    )
            return None
        challenge = next(
            (o for o in new_outputs if o.agent_id == critic.agent_id), None
        )
        return new_outputs, report, challenge

    async def _send_event(
        self,
        callback: Callable[[dict], Awaitable[None]] | None,
        event: dict,
    ):
        """Forward a recorder-built wire event to the frontend callback."""
        if callback:
            try:
                await callback(event)
            except Exception as e:  # noqa: BLE001 — a broken callback must not kill the run
                logger.error(f"Orchestrator │ Progress callback error: {e}")
