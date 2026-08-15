"""
Assembly — Agent Manager

Creates and manages agent instances. Maps roles to agent classes.
Runs agents concurrently using asyncio.
"""

import asyncio
from typing import List, Dict, Optional

from src.agents.base_agent import BaseAgent, AgentOutput
from src.agents.solver import SolverAgent
from src.agents.researcher import ResearcherAgent
from src.agents.critic import CriticAgent
from src.agents.synthesizer import SynthesizerAgent
from src.providers.router import ModelRouter
from src.orchestration.workspace import workspace, WorkspaceEvent, EventType
from src.core.logging_config import logger


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
        self.agents: Dict[str, BaseAgent] = {}
        self._agent_counter = 0

    def create_agent(
        self,
        agent_type: str,
        role_description: str = "",
        problem_type: str = "general",
        complexity: str = "medium",
        time_budget_minutes: int = 5,
        prefer_provider: Optional[str] = None,
    ) -> BaseAgent:
        """
        Create a new agent with the appropriate model.
        
        The Model Router selects the best provider/model for this
        agent type and task requirements.
        """
        self._agent_counter += 1
        agent_id = f"agent_{self._agent_counter:02d}"

        # Get the agent class
        agent_cls = AGENT_CLASSES.get(agent_type, SolverAgent)

        # Route to the best model
        assignment = self.router.route(
            agent_type=agent_type,
            problem_type=problem_type,
            complexity=complexity,
            time_budget_minutes=time_budget_minutes,
            prefer_provider=prefer_provider,
        )

        agent = agent_cls(
            agent_id=agent_id,
            provider=assignment.provider,
            model=assignment.model,
            role_description=role_description,
        )

        self.agents[agent_id] = agent
        logger.info(
            f"AgentMgr │ Created {agent_id}: {agent_type} → "
            f"{assignment.provider_name}/{assignment.model}"
        )

        return agent

    def create_team(
        self,
        team_composition: List[Dict[str, str]],
        problem_type: str = "general",
        complexity: str = "medium",
        time_budget_minutes: int = 5,
    ) -> List[BaseAgent]:
        """
        Create an entire team from a composition plan.
        
        Args:
            team_composition: List of {agent_type, role_description} dicts.
        
        Returns:
            List of created agent instances.
        """
        agents = []
        available_providers = self.router.get_available_providers()

        for i, spec in enumerate(team_composition):
            # Rotate providers for diversity (prevent echo chamber)
            prefer_provider = available_providers[i % len(available_providers)] if available_providers else None

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
        agents: List[BaseAgent],
        question: str,
    ) -> List[AgentOutput]:
        """
        Run all agents independently in parallel (Stage 1).
        
        Each agent works independently and cannot see others' answers yet,
        reducing early groupthink (PRD Section 6.1).
        """
        logger.info(f"AgentMgr │ Running {len(agents)} agents independently")

        tasks = [agent.run(question) for agent in agents]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        outputs = []
        for i, result in enumerate(results):
            if isinstance(result, Exception):
                logger.error(f"AgentMgr │ {agents[i].agent_id} failed: {result}")
                # Create a low-confidence fallback output
                outputs.append(AgentOutput(
                    agent_id=agents[i].agent_id,
                    agent_type=agents[i].agent_type,
                    position="Unable to complete analysis due to an error.",
                    confidence=0.1,
                    reasoning=f"Error: {str(result)}",
                ))
            else:
                outputs.append(result)
                # Publish to workspace
                await workspace.publish(WorkspaceEvent(
                    event_type=EventType.SOLUTION,
                    agent_id=result.agent_id,
                    execution_id=self.execution_id,
                    round_number=0,
                    data=result.to_dict(),
                ))

        return outputs

    def get_agent_info(self) -> List[Dict]:
        """Get summary info about all created agents."""
        return [
            {
                "agent_id": agent.agent_id,
                "agent_type": agent.agent_type,
                "model": agent.model,
                "role_description": agent.role_description,
            }
            for agent in self.agents.values()
        ]
