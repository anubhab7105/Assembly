"""
Assembly — Debate Manager

Runs cross-agent debate rounds. Each agent reviews others' conclusions
and produces critiques. Enforces that every round adds value (PRD Section 7.3).
"""

import asyncio
from typing import List, Dict, Optional

from src.agents.base_agent import BaseAgent, AgentOutput
from src.orchestration.workspace import workspace, WorkspaceEvent, EventType
from src.core.logging_config import logger


class DebateManager:
    """
    Manages multi-round agent debates.
    
    In each round:
    1. Each agent sees ALL other agents' latest positions
    2. Each agent produces a critique / updated position
    3. Results are published to the shared workspace
    
    Every round must resolve a disagreement, add evidence,
    improve a solution, remove an error, or increase confidence —
    not produce conversational filler (PRD Section 7.3).
    """

    def __init__(self, execution_id: str):
        self.execution_id = execution_id

    async def run_debate_round(
        self,
        agents: List[BaseAgent],
        current_outputs: List[AgentOutput],
        question: str,
        round_number: int,
    ) -> List[AgentOutput]:
        """
        Run one debate round: all agents review each other's work in parallel.
        
        Args:
            agents: Active agent instances.
            current_outputs: Each agent's latest output.
            question: Original user question.
            round_number: Current round number.
        
        Returns:
            Updated list of AgentOutput after debate.
        """
        logger.info(f"Debate  │ Round {round_number} — {len(agents)} agents debating")

        # Build mapping of agent_id → output for quick lookup
        output_map = {o.agent_id: o for o in current_outputs}

        # Each agent critiques all others IN PARALLEL
        tasks = []
        for agent in agents:
            # Filter out this agent's own output — they review everyone else
            others = [o for o in current_outputs if o.agent_id != agent.agent_id]
            if others:
                tasks.append(self._agent_critique(agent, question, others, round_number))
            else:
                # No others to critique — re-run independently
                tasks.append(agent.run(question))

        # Run all critiques concurrently
        results = await asyncio.gather(*tasks, return_exceptions=True)

        # Collect valid results
        updated_outputs = []
        for i, result in enumerate(results):
            if isinstance(result, Exception):
                logger.error(f"Debate  │ Agent {agents[i].agent_id} failed: {result}")
                # Keep the agent's previous output
                prev = output_map.get(agents[i].agent_id)
                if prev:
                    updated_outputs.append(prev)
            else:
                updated_outputs.append(result)
                # Publish to workspace
                await workspace.publish(WorkspaceEvent(
                    event_type=EventType.CRITIQUE,
                    agent_id=result.agent_id,
                    execution_id=self.execution_id,
                    round_number=round_number,
                    data=result.to_dict(),
                ))

        logger.info(f"Debate  │ Round {round_number} complete — {len(updated_outputs)} outputs")
        return updated_outputs

    async def _agent_critique(
        self,
        agent: BaseAgent,
        question: str,
        others: List[AgentOutput],
        round_number: int,
    ) -> AgentOutput:
        """Have a single agent critique others' work."""
        return await agent.critique(question, others, round_number)
