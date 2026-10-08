"""
Assembly — Agent Manager

Creates and manages agent instances. Maps roles to agent classes.
Runs agents concurrently using asyncio.
"""

import asyncio

from src.agents.base_agent import AgentOutput, BaseAgent
from src.agents.critic import CriticAgent
from src.agents.researcher import ResearcherAgent
from src.agents.solver import SolverAgent
from src.agents.synthesizer import SynthesizerAgent
from src.core.logging_config import logger
from src.orchestration.time_controller import TaskTracker
from src.orchestration.workspace import EventType, WorkspaceEvent, workspace
from src.providers.errors import ProviderDown, RateLimited
from src.providers.quota import QuotaExhausted
from src.providers.router import ModelRouter

# Failures worth one retry on a fallback model (transient by nature).
RETRYABLE_ERRORS = (RateLimited, QuotaExhausted, ProviderDown)


# Agent type → class mapping
AGENT_CLASSES = {
    "solver": SolverAgent,
    "researcher": ResearcherAgent,
    "critic": CriticAgent,
    "synthesizer": SynthesizerAgent,
}


class AgentManager:
    """
    Creates, manages, and runs agent instances.

    Handles:
    - Agent instantiation with appropriate models
    - Parallel execution via asyncio
    - Workspace event publishing
    """

    def __init__(self, router: ModelRouter, execution_id: str):
        self.router = router
        self.execution_id = execution_id
        self.agents: dict[str, BaseAgent] = {}
        self._decisions: dict[str, object] = {}
        self.last_routing: object = None
        self._agent_counter = 0

    def create_agent(
        self,
        agent_type: str,
        role_description: str = "",
        problem_type: str = "general",
        complexity: str = "medium",
        time_budget_minutes: int = 5,
        prefer_provider: str | None = None,
    ) -> BaseAgent:
        """
        Create a new agent with the appropriate model.

        The Model Router selects the best provider/model for this
        agent type and task requirements.
        """
        self._agent_counter += 1
        agent_id = f"agent_{self._agent_counter:02d}"

        # Route to the best model
        assignment = self.router.route(
            agent_type=agent_type,
            problem_type=problem_type,
            complexity=complexity,
            time_budget_minutes=time_budget_minutes,
            prefer_provider=prefer_provider,
        )

        return self._instantiate(
            {"agent_type": agent_type, "role_description": role_description},
            assignment,
            agent_id=agent_id,
        )

    def _instantiate(
        self, spec: dict[str, str], decision, agent_id: str | None = None
    ) -> BaseAgent:
        """Build one agent from a routing decision, keeping the agent id stable."""
        if agent_id is None:
            self._agent_counter += 1
            agent_id = f"agent_{self._agent_counter:02d}"

        agent_cls = AGENT_CLASSES.get(spec["agent_type"], SolverAgent)
        agent = agent_cls(
            agent_id=agent_id,
            provider=decision.provider,
            model=decision.model,
            role_description=spec.get("role_description", ""),
            router=self.router,
            routing=decision,
            family=getattr(decision, "family", ""),
        )

        self.agents[agent_id] = agent
        self._decisions[agent_id] = decision
        logger.info(
            f"AgentMgr │ Created {agent_id}: {spec['agent_type']} → "
            f"{decision.provider_name}/{decision.model}"
        )
        return agent

    def create_team(
        self,
        team_composition: list[dict[str, str]],
        problem_type: str = "general",
        complexity: str = "medium",
        time_budget_minutes: int = 5,
    ) -> list[BaseAgent]:
        """
        Create an entire team from a composition plan.

        Uses family-aware team routing when the router offers route_team();
        otherwise falls back to per-agent routing with provider rotation.

        Args:
            team_composition: List of {agent_type, role_description} dicts.

        Returns:
            List of created agent instances.
        """
        specs = [
            {
                "agent_type": spec["agent_type"],
                "role_description": spec.get("role_description", ""),
            }
            for spec in team_composition
        ]
        route_team = getattr(self.router, "route_team", None)
        if route_team is None:
            return self._create_team_legacy(
                specs, problem_type, complexity, time_budget_minutes
            )

        routing = route_team(specs, problem_type, complexity, time_budget_minutes)
        self.last_routing = routing
        return [
            self._instantiate(spec, decision)
            for spec, decision in zip(specs, routing.decisions)
        ]

    def _create_team_legacy(
        self,
        specs: list[dict[str, str]],
        problem_type: str,
        complexity: str,
        time_budget_minutes: int,
    ) -> list[BaseAgent]:
        """Per-agent routing with provider rotation (routers without route_team)."""
        agents = []
        available_providers = self.router.get_available_providers()

        for i, spec in enumerate(specs):
            # Rotate providers for diversity (prevent echo chamber)
            prefer_provider = (
                available_providers[i % len(available_providers)]
                if available_providers
                else None
            )

            agent = self.create_agent(
                agent_type=spec["agent_type"],
                role_description=spec.get("role_description", ""),
                problem_type=problem_type,
                complexity=complexity,
                time_budget_minutes=time_budget_minutes,
                prefer_provider=prefer_provider,
            )
            agents.append(agent)

        return agents

    async def run_all_independent(
        self,
        agents: list[BaseAgent],
        question: str,
        timeout_s: float | None = None,
        tracker: TaskTracker | None = None,
    ) -> list[AgentOutput]:
        """
        Run all agents independently in parallel (Stage 1).

        Each agent works independently and cannot see others' answers yet,
        reducing early groupthink (PRD Section 6.1).

        Args:
            timeout_s: per-agent wall-clock bound (stragglers time out into
                low-confidence fallback outputs instead of hanging the run).
            tracker: task registry for bulk cancel + leak detection. A local
                one is used when omitted; either way no task outlives this
                call — the finally-drain awaits every straggler.
        """
        logger.info(f"AgentMgr │ Running {len(agents)} agents independently")

        own_tracker = (
            tracker
            if tracker is not None
            else TaskTracker(owner=f"{self.execution_id}:solve")
        )
        tasks = [
            own_tracker.create(
                self._run_one(agent, question, timeout_s),
                name=f"assembly:{self.execution_id}:{agent.agent_id}",
            )
            for agent in agents
        ]
        try:
            results = await asyncio.gather(*tasks, return_exceptions=True)
        finally:
            # Stragglers (timed-out or cancelled) are awaited here so none
            # leak past this phase, even when this task itself is cancelled.
            await own_tracker.drain()

        outputs = []
        for i, result in enumerate(results):
            if isinstance(result, Exception):
                logger.error(f"AgentMgr │ {agents[i].agent_id} failed: {result}")
                # Create a low-confidence fallback output
                outputs.append(
                    AgentOutput(
                        agent_id=agents[i].agent_id,
                        agent_type=agents[i].agent_type,
                        position="Unable to complete analysis due to an error.",
                        reasoning_summary="Agent run failed; see server logs.",
                        confidence=0.1,
                        confidence_raw=0.1,
                    )
                )
            else:
                outputs.append(result)
                # Publish to workspace
                await workspace.publish(
                    WorkspaceEvent(
                        event_type=EventType.SOLUTION,
                        agent_id=result.agent_id,
                        execution_id=self.execution_id,
                        round_number=0,
                        data=result.to_dict(),
                    )
                )

        return outputs

    async def _run_one(
        self, agent: BaseAgent, question: str, timeout_s: float | None
    ) -> AgentOutput:
        """One agent run, bounded by the per-call timeout when given.

        asyncio.timeout converts the expiry to TimeoutError (never
        CancelledError), so user cancellation still propagates distinctly
        and the manager's error-output path handles the timeout.
        """
        if timeout_s is None:
            return await self._run_with_retry(agent, question)
        async with asyncio.timeout(timeout_s):
            return await self._run_with_retry(agent, question)

    async def _run_with_retry(self, agent: BaseAgent, question: str) -> AgentOutput:
        """Run one agent, retrying once on a fallback model after transient
        provider failures (rate limit, quota, outage). The agent id stays
        stable so supports/disagrees_with references keep working."""
        try:
            return await agent.run(question)
        except RETRYABLE_ERRORS as e:
            decision = self._decisions.get(agent.agent_id)
            fallback = None
            router_fallback = getattr(self.router, "fallback_for", None)
            if decision is not None and router_fallback is not None:
                try:
                    fallback = router_fallback(decision, e)
                except Exception:  # noqa: BLE001 — fall through to the error path
                    fallback = None
            if fallback is None:
                raise
            logger.info(
                f"AgentMgr │ {agent.agent_id} retrying on "
                f"{fallback.provider_name}/{fallback.model} after {type(e).__name__}"
            )
            retry_agent = type(agent)(
                agent_id=agent.agent_id,
                provider=fallback.provider,
                model=fallback.model,
                role_description=agent.role_description,
                router=self.router,
                routing=fallback,
                family=getattr(fallback, "family", ""),
            )
            if hasattr(agent, "search_results"):
                retry_agent.search_results = agent.search_results
            self.agents[agent.agent_id] = retry_agent
            self._decisions[agent.agent_id] = fallback
            return await retry_agent.run(question)

    def get_agent_info(self) -> list[dict]:
        """Get summary info about all created agents, incl. routing provenance."""
        info = []
        for agent in self.agents.values():
            decision = self._decisions.get(agent.agent_id)
            info.append(
                {
                    "agent_id": agent.agent_id,
                    "agent_type": agent.agent_type,
                    "model": agent.model,
                    "provider_name": agent.provider.provider_name,
                    "role_description": agent.role_description,
                    "family": getattr(decision, "family", ""),
                    "role": getattr(decision, "role", "") or agent.agent_type,
                    "reason": getattr(decision, "reason", ""),
                }
            )
        return info
