"""
Assembly — Main Orchestrator

The central engine that manages the full execution lifecycle:
Question → Planning → Team Formation → Independent Solving →
Debate → Consensus → Synthesis → Final Answer

This is the core of Assembly (PRD Section 9.2).
"""

import asyncio
import time
from datetime import datetime, timezone
from typing import Optional, Callable, Awaitable, List, Dict

from src.orchestration.planner import Planner, PlanResult
from src.orchestration.agent_manager import AgentManager
from src.orchestration.consensus import ConsensusEngine, ConsensusResult
from src.orchestration.debate import DebateManager
from src.orchestration.budget_controller import BudgetController
from src.orchestration.workspace import workspace
from src.agents.base_agent import AgentOutput
from src.agents.synthesizer import SynthesizerAgent
from src.providers.router import ModelRouter
from src.research.search import SearchEngine
from src.core.logging_config import logger


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
        providers_used: list = None,
        status: str = "completed",
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

    async def execute(
        self,
        execution_id: str,
        question: str,
        time_budget_minutes: int,
        on_progress: Optional[Callable[[dict], Awaitable[None]]] = None,
    ) -> ExecutionResult:
        """
        Run the full orchestration pipeline.
        
        Args:
            execution_id: Unique execution identifier.
            question: User's question.
            time_budget_minutes: Time budget (3/5/10/15 minutes).
            on_progress: Async callback for real-time progress events.
        """
        logger.info(f"═══ EXECUTION START: {execution_id} ═══")
        logger.info(f"Question: {question[:100]}...")
        logger.info(f"Budget: {time_budget_minutes} minutes")

        # Initialize components
        budget = BudgetController(time_budget_minutes)
        consensus_engine = ConsensusEngine()
        planner = Planner(self.router)
        agent_manager = AgentManager(self.router, execution_id)
        debate_manager = DebateManager(execution_id)

        total_tokens = 0

        try:
            # ════════════════════════════════════════════════════════════
            # PHASE 1: PLANNING — Classify the problem
            # ════════════════════════════════════════════════════════════
            await self._emit_progress(on_progress, execution_id, "status_update", {
                "status": "planning",
                "message": "Analyzing your question...",
            })

            plan = await planner.plan(question, time_budget_minutes)

            await self._emit_progress(on_progress, execution_id, "status_update", {
                "status": "planning",
                "message": f"Classified as {plan.complexity} complexity {plan.problem_type} problem",
                "problem_type": plan.problem_type,
                "complexity": plan.complexity,
            })

            # ════════════════════════════════════════════════════════════
            # PHASE 2: TEAM FORMATION — Create agents
            # ════════════════════════════════════════════════════════════
            await self._emit_progress(on_progress, execution_id, "status_update", {
                "status": "forming_team",
                "message": f"Assembling a team of {len(plan.team_composition)} experts...",
            })

            agents = agent_manager.create_team(
                team_composition=plan.team_composition,
                problem_type=plan.problem_type,
                complexity=plan.complexity,
                time_budget_minutes=time_budget_minutes,
            )

            for agent in agents:
                budget.record_agent_created()

            # Send agent info to frontend
            agent_info = agent_manager.get_agent_info()

            # Track which providers are being used
            providers_used = list(set(a.get("provider_name", "unknown") for a in agent_info))

            await self._emit_progress(on_progress, execution_id, "agent_update", {
                "agents": agent_info,
                "message": "Team assembled",
            })

            # ════════════════════════════════════════════════════════════
            # PHASE 3: WEB RESEARCH (if needed)
            # ════════════════════════════════════════════════════════════
            search_results = []
            if plan.needs_research and budget.can_search():
                await self._emit_progress(on_progress, execution_id, "status_update", {
                    "status": "researching",
                    "message": "Searching for evidence...",
                })

                search_results = await self.search_engine.search(question)
                budget.record_search(len(search_results))

            # ════════════════════════════════════════════════════════════
            # PHASE 4: INDEPENDENT SOLVING — Each agent works alone
            # ════════════════════════════════════════════════════════════
            await self._emit_progress(on_progress, execution_id, "status_update", {
                "status": "solving",
                "message": "Agents solving independently...",
                **budget.get_status(),
            })

            # Inject search results for researcher agents
            for agent in agents:
                if hasattr(agent, 'search_results'):
                    agent.search_results = search_results

            outputs = await agent_manager.run_all_independent(agents, question)

            # Aggregate token usage from independent solving phase
            for o in outputs:
                total_tokens += o.tokens_used
            budget.record_tokens(sum(o.tokens_used for o in outputs))

            # ════════════════════════════════════════════════════════════
            # PHASE 5: DEBATE — Cross-agent critique rounds
            # ════════════════════════════════════════════════════════════
            round_number = 1
            consensus_result = consensus_engine.evaluate(outputs, round_number)

            await self._emit_progress(on_progress, execution_id, "consensus_update", {
                "consensus_score": consensus_result.score,
                "round": round_number,
                "decision": consensus_result.decision,
                **budget.get_status(),
            })

            # Debate loop: continue while consensus is insufficient and budget allows
            while (
                consensus_result.decision == "continue"
                and budget.can_debate()
                and not budget.should_force_synthesis()
            ):
                round_number += 1

                await self._emit_progress(on_progress, execution_id, "status_update", {
                    "status": "debating",
                    "message": f"Debate round {round_number}...",
                    "round": round_number,
                    **budget.get_status(),
                })

                # Run debate round
                outputs = await debate_manager.run_debate_round(
                    agents=agents,
                    current_outputs=outputs,
                    question=question,
                    round_number=round_number,
                )
                budget.record_debate_round()

                # Aggregate token usage from debate round
                round_tokens = sum(o.tokens_used for o in outputs)
                total_tokens += round_tokens
                budget.record_tokens(round_tokens)

                # Re-evaluate consensus
                force = budget.should_force_synthesis()
                consensus_result = consensus_engine.evaluate(
                    outputs, round_number, force_finalize=force,
                )

                await self._emit_progress(on_progress, execution_id, "consensus_update", {
                    "consensus_score": consensus_result.score,
                    "round": round_number,
                    "decision": consensus_result.decision,
                    "reasoning": consensus_result.reasoning,
                    **budget.get_status(),
                })

            # ════════════════════════════════════════════════════════════
            # PHASE 6: FINAL SYNTHESIS — Produce the answer
            # ════════════════════════════════════════════════════════════
            await self._emit_progress(on_progress, execution_id, "status_update", {
                "status": "synthesizing",
                "message": "Synthesizing final answer...",
                "consensus_score": consensus_result.score,
                **budget.get_status(),
            })

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
            sources = final_output.sources
            if not sources:
                # Collect sources from all agents
                for o in outputs:
                    sources.extend(o.sources)

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
            )

            await self._emit_progress(on_progress, execution_id, "answer_ready", {
                "status": "completed",
                "answer": result.answer,
                "sources": result.sources,
                "consensus_score": result.consensus_score,
                "agent_count": result.agent_count,
                "providers_used": result.providers_used,
                **budget.get_status(),
            })

            logger.info(
                f"═══ EXECUTION COMPLETE: {execution_id} ═══\n"
                f"    Consensus: {consensus_result.score:.0%}\n"
                f"    Agents: {len(agents)}\n"
                f"    Debate rounds: {round_number}\n"
                f"    Time: {budget.state.elapsed_seconds:.1f}s"
            )

            # Cleanup workspace
            workspace.cleanup(execution_id)

            return result

        except Exception as e:
            logger.error(f"═══ EXECUTION FAILED: {execution_id} — {e} ═══")
            await self._emit_progress(on_progress, execution_id, "error", {
                "status": "failed",
                "message": str(e),
            })
            workspace.cleanup(execution_id)
            return ExecutionResult(
                answer=f"An error occurred while processing your question: {str(e)}",
                sources=[],
                consensus_score=0.0,
                problem_type="unknown",
                complexity="unknown",
                agent_count=0,
                debate_rounds=0,
                total_tokens=0,
                status="failed",
            )

    async def _emit_progress(
        self,
        callback: Optional[Callable[[dict], Awaitable[None]]],
        execution_id: str,
        event_type: str,
        data: dict,
    ):
        """Send a progress event to the frontend via callback."""
        if callback:
            try:
                await callback({
                    "event_type": event_type,
                    "execution_id": execution_id,
                    "data": data,
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                })
            except Exception as e:
                logger.error(f"Orchestrator │ Progress callback error: {e}")
