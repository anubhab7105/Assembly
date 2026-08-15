"""
Assembly — Planner

Classifies the problem type and complexity, then determines
the optimal team composition (PRD Section 7.1, 7.9).
"""

import json
from typing import Dict, List, Optional

from src.providers.base import ChatMessage
from src.providers.router import ModelRouter, ModelAssignment
from src.core.logging_config import logger


class PlanResult:
    """Result of the planning phase."""

    def __init__(
        self,
        problem_type: str,
        complexity: str,
        team_composition: List[Dict[str, str]],
        needs_research: bool,
        reasoning: str,
    ):
        self.problem_type = problem_type  # math | coding | research | general | multi_step
        self.complexity = complexity  # low | medium | high
        self.team_composition = team_composition  # [{agent_type, role_description}]
        self.needs_research = needs_research
        self.reasoning = reasoning

    def to_dict(self) -> dict:
        return {
            "problem_type": self.problem_type,
            "complexity": self.complexity,
            "team_composition": self.team_composition,
            "needs_research": self.needs_research,
            "reasoning": self.reasoning,
        }


class Planner:
    """
    Problem classifier and team formation planner.
    
    Uses an LLM call to classify the question, then determines
    the optimal team based on complexity and time budget.
    """

    CLASSIFICATION_PROMPT = """You are the Planner for Assembly, a multi-agent AI reasoning system.

Analyze the user's question and determine:
1. Problem type: one of [math, coding, research, general, multi_step]
2. Complexity: one of [low, medium, high]
3. Whether web research is needed (true/false)
4. The ideal team composition

TEAM ROLES AVAILABLE:
- solver: Independent problem-solving and analysis
- researcher: Evidence gathering and research
- critic: Finding flaws, challenging assumptions, devil's advocate
- synthesizer: Final answer synthesis (always included, don't list it)

COMPLEXITY GUIDELINES:
- LOW: Simple factual questions, basic explanations → 2 agents + synthesizer
- MEDIUM: Comparisons, moderate analysis, multi-part questions → 3 agents + synthesizer
- HIGH: Deep research, complex reasoning, controversial topics → 4+ agents + synthesizer

Respond with JSON only:
```json
{
    "problem_type": "general",
    "complexity": "medium",
    "needs_research": false,
    "team": [
        {"agent_type": "solver", "role_description": "Core problem solver"},
        {"agent_type": "researcher", "role_description": "Evidence gatherer"},
        {"agent_type": "critic", "role_description": "Assumption challenger"}
    ],
    "reasoning": "Brief explanation of why this team composition was chosen"
}
```"""

    def __init__(self, router: ModelRouter):
        self.router = router

    async def plan(self, question: str, time_budget_minutes: int) -> PlanResult:
        """
        Classify the problem and determine team composition.
        
        Args:
            question: The user's question.
            time_budget_minutes: How much time is available.
        
        Returns:
            PlanResult with problem classification and team composition.
        """
        logger.info(f"Planner │ Classifying question (budget: {time_budget_minutes}min)")

        # Get a model for planning
        assignment = self.router.route_for_planning()

        messages = [
            ChatMessage(role="system", content=self.CLASSIFICATION_PROMPT),
            ChatMessage(
                role="user",
                content=f"Time budget: {time_budget_minutes} minutes\n\nQuestion: {question}",
            ),
        ]

        try:
            response = await assignment.provider.generate(
                messages=messages,
                model=assignment.model,
                temperature=0.1,
                max_tokens=1024,
            )

            plan = self._parse_plan(response.content, time_budget_minutes)
            logger.info(
                f"Planner │ Type={plan.problem_type}, Complexity={plan.complexity}, "
                f"Team={len(plan.team_composition)} agents, Research={plan.needs_research}"
            )
            return plan

        except Exception as e:
            logger.error(f"Planner │ Classification failed: {e}")
            return self._default_plan(time_budget_minutes)

    def _parse_plan(self, content: str, time_budget_minutes: int) -> PlanResult:
        """Parse the LLM's classification response."""
        try:
            json_str = content.strip()
            if "```json" in json_str:
                json_str = json_str.split("```json")[1].split("```")[0].strip()
            elif "```" in json_str:
                json_str = json_str.split("```")[1].split("```")[0].strip()

            data = json.loads(json_str)

            team = data.get("team", [])

            # Enforce budget limits on team size
            max_agents = self._max_agents_for_budget(time_budget_minutes)
            if len(team) > max_agents:
                team = team[:max_agents]

            return PlanResult(
                problem_type=data.get("problem_type", "general"),
                complexity=data.get("complexity", "medium"),
                team_composition=team,
                needs_research=data.get("needs_research", False),
                reasoning=data.get("reasoning", ""),
            )
        except (json.JSONDecodeError, KeyError, IndexError) as e:
            logger.warning(f"Planner │ Parse failed: {e}, using default plan")
            return self._default_plan(time_budget_minutes)

    def _default_plan(self, time_budget_minutes: int) -> PlanResult:
        """Fallback plan if classification fails."""
        if time_budget_minutes <= 3:
            team = [
                {"agent_type": "solver", "role_description": "Problem solver"},
                {"agent_type": "critic", "role_description": "Answer verifier"},
            ]
        else:
            team = [
                {"agent_type": "solver", "role_description": "Problem solver"},
                {"agent_type": "researcher", "role_description": "Evidence gatherer"},
                {"agent_type": "critic", "role_description": "Assumption challenger"},
            ]

        return PlanResult(
            problem_type="general",
            complexity="medium",
            team_composition=team,
            needs_research=False,
            reasoning="Default plan (classification unavailable).",
        )

    @staticmethod
    def _max_agents_for_budget(minutes: int) -> int:
        """Maximum team members based on time budget."""
        if minutes <= 3:
            return 2
        elif minutes <= 5:
            return 3
        elif minutes <= 10:
            return 4
        else:
            return 5
