"""
Assembly — Planner (docs/WORKFLOW.md section 3).

Classifies the question into a validated PlanSchema, then derives the
team composition from it.

Resilience chain (planning must never fail the run):
1. One LLM call on the cheapest fast planner model
   (``route_for_planning`` returns the first usable catalog model, and
   models.yaml lists the fastest/cheapest model first per provider).
2. Schema validation; on invalid JSON exactly ONE retry, routed to a
   fallback model when the router offers one, with the error message
   included so the model can repair its reply.
3. A heuristic fallback classifier (keywords + length) — deterministic,
   no network, always returns a usable plan.

Suggested roles are capped by what the capacity planner allows (tier
ceilings always; quota-aware trim when the router exposes a quota
snapshot). The capacity planner still has the final say downstream.
"""

import json
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator

from src.agents.base_agent import BaseAgent
from src.core.logging_config import logger
from src.orchestration.capacity import (
    MIN_ROUNDS,
    TIER_MAX_AGENTS,
    TIER_MAX_ROUNDS,
    VALID_TIERS,
    KeyBudget,
    PlannerSuggestion,
    heuristic_suggestion,
    plan_capacity,
)
from src.providers.base import ChatMessage
from src.providers.router import ModelRouter

KNOWN_PROBLEM_TYPES: tuple[str, ...] = (
    "math",
    "coding",
    "research",
    "general",
    "multi_step",
)

KNOWN_ROLES: tuple[str, ...] = ("solver", "researcher", "critic")

ROLE_DESCRIPTIONS: dict[str, str] = {
    "solver": "Independent problem solver",
    "researcher": "Evidence gatherer",
    "critic": "Assumption challenger",
}

_MATH_HINTS: tuple[str, ...] = (
    "calculate",
    "calculation",
    "equation",
    "integral",
    "derivative",
    "theorem",
    "proof",
    "algebra",
    "geometry",
    "probability",
    "statistic",
    "percent",
)

_CODING_HINTS: tuple[str, ...] = (
    "code",
    "function",
    " bug",
    "debug",
    "python",
    "javascript",
    "typescript",
    "compile",
    "algorithm",
    "regex",
    "sql",
    "refactor",
    "program",
)

_MULTISTEP_HINTS: tuple[str, ...] = (
    "step by step",
    "step-by-step",
    "roadmap",
    "pipeline",
    "workflow",
    "project plan",
)


class PlanSchema(BaseModel):
    """Validated planner output (WORKFLOW section 3)."""

    model_config = ConfigDict(extra="ignore")

    problem_type: str = Field(default="general", min_length=1, max_length=64)
    complexity: Literal["low", "medium", "high"] = "medium"
    needs_research: bool = False
    needs_code_execution: bool = False
    suggested_roles: list[Literal["solver", "researcher", "critic"]] = Field(
        default_factory=lambda: ["solver", "critic"]
    )
    estimated_rounds: int = Field(default=1, ge=1, le=8)

    @field_validator("problem_type")
    @classmethod
    def _known_problem_type(cls, value: str) -> str:
        normalized = value.strip().lower()
        if normalized in KNOWN_PROBLEM_TYPES:
            return normalized
        return "general"


class PlanResult:
    """Result of the planning phase (team view derived from PlanSchema)."""

    def __init__(
        self,
        problem_type: str,
        complexity: str,
        team_composition: list[dict[str, str]],
        needs_research: bool,
        reasoning: str,
        capacity: dict[str, object] | None = None,
        suggested_roles: list[str] | None = None,
        estimated_rounds: int = 1,
        needs_code_execution: bool = False,
        fallback_used: bool = False,
    ):
        self.problem_type = problem_type
        self.complexity = complexity  # low | medium | high
        self.team_composition = team_composition  # [{agent_type, role_description}]
        self.needs_research = needs_research
        self.reasoning = reasoning
        self.capacity = capacity  # affordable-call estimate (may be None)
        self.suggested_roles = (
            list(suggested_roles)
            if suggested_roles is not None
            else [m["agent_type"] for m in team_composition]
        )
        self.estimated_rounds = estimated_rounds
        self.needs_code_execution = needs_code_execution
        self.fallback_used = fallback_used

    def to_dict(self) -> dict:
        return {
            "problem_type": self.problem_type,
            "complexity": self.complexity,
            "team_composition": self.team_composition,
            "needs_research": self.needs_research,
            "reasoning": self.reasoning,
            "capacity": self.capacity,
            "suggested_roles": self.suggested_roles,
            "estimated_rounds": self.estimated_rounds,
            "needs_code_execution": self.needs_code_execution,
            "fallback_used": self.fallback_used,
        }


class Planner:
    """
    Problem classifier and team formation planner.

    Uses the cheapest fast model for one classification call, validates the
    JSON against PlanSchema (one retry on invalid JSON), and falls back to
    a heuristic classifier so planning never fails the run.
    """

    CLASSIFICATION_PROMPT = """You are the Planner for Assembly, a multi-agent AI reasoning system.

Analyze the user's question and determine:
1. Problem type: one of [math, coding, research, general, multi_step]
2. Complexity: one of [low, medium, high]
3. Whether web research is needed (true/false)
4. Whether code execution is needed (true/false)
5. The ideal team roles and debate rounds

TEAM ROLES AVAILABLE (pick 2-6, never list synthesizer — it is always added later):
- solver: Independent problem-solving and analysis
- researcher: Evidence gathering and research
- critic: Finding flaws, challenging assumptions, devil's advocate

COMPLEXITY GUIDELINES:
- LOW: Simple factual questions, basic explanations → 2 solver/critic roles, 1 round
- MEDIUM: Comparisons, moderate analysis, multi-part questions → 3 roles, 2 rounds
- HIGH: Deep research, complex reasoning, controversial topics → 4+ roles including researcher, 2+ rounds

Respond with JSON only:
```json
{
    "problem_type": "general",
    "complexity": "medium",
    "needs_research": false,
    "needs_code_execution": false,
    "suggested_roles": ["solver", "researcher", "critic"],
    "estimated_rounds": 2
}
```"""

    def __init__(self, router: ModelRouter):
        self.router = router

    async def plan(self, question: str, time_budget_minutes: int) -> PlanResult:
        """
        Classify the problem and determine team composition.

        Never raises: every failure path ends in the heuristic fallback.

        Args:
            question: The user's question.
            time_budget_minutes: How much time is available.

        Returns:
            PlanResult with validated classification and team composition.
        """
        question = question or ""
        logger.info(
            f"Planner │ Classifying question (budget: {time_budget_minutes}min)"
        )

        try:
            assignment = self.router.route_for_planning()
        except Exception as e:  # noqa: BLE001 — planning must fall back, never crash
            logger.error(f"Planner │ Planner routing failed: {e}")
            plan = self._heuristic_plan(
                question, time_budget_minutes, "no planner model"
            )
            plan.capacity = self._read_capacity(time_budget_minutes)
            return plan

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
                max_tokens=512,
            )
            try:
                schema, reasoning = self._parse_and_validate(response.content)
            except (ValueError, TypeError) as first_error:
                logger.warning(
                    f"Planner │ First plan invalid ({first_error}); retrying once"
                )
                retry_response = await self._retry_generate(
                    assignment, messages, first_error
                )
                schema, reasoning = self._parse_and_validate(retry_response.content)

            plan = self._apply_capacity(schema, reasoning, time_budget_minutes)
            plan.capacity = self._read_capacity(time_budget_minutes)
            logger.info(
                f"Planner │ Type={plan.problem_type}, Complexity={plan.complexity}, "
                f"Team={len(plan.team_composition)} agents, Research={plan.needs_research}"
            )
            return plan

        except Exception as e:  # noqa: BLE001 — planning must fall back, never crash
            logger.error(
                f"Planner │ Classification failed ({e}); using heuristic fallback"
            )
            plan = self._heuristic_plan(question, time_budget_minutes, str(e))
            plan.capacity = self._read_capacity(time_budget_minutes)
            return plan

    async def _retry_generate(
        self, assignment: Any, messages: list[ChatMessage], error: Exception
    ) -> Any:
        """Repeat the classification once, preferring a fallback model.

        Falls back to the original assignment when the router offers no
        alternative (e.g. duck-typed test routers without fallback_for).
        """
        retry_assignment = assignment
        fallback_for = getattr(self.router, "fallback_for", None)
        if callable(fallback_for):
            try:
                alternative = fallback_for(assignment, error)
                if alternative is not None:
                    retry_assignment = alternative
                    logger.info(
                        "Planner │ Retrying with fallback "
                        f"{retry_assignment.provider_name}/{retry_assignment.model}"
                    )
            except Exception as e:  # noqa: BLE001 — retry must proceed regardless
                logger.warning(f"Planner │ Fallback routing failed: {e}")

        retry_messages = [
            *messages,
            ChatMessage(
                role="user",
                content=(
                    "Your previous reply was invalid: "
                    f"{error}. Reply with JSON only, exactly matching the schema."
                ),
            ),
        ]
        return await retry_assignment.provider.generate(
            messages=retry_messages,
            model=retry_assignment.model,
            temperature=0.1,
            max_tokens=512,
        )

    def _parse_and_validate(self, content: str) -> tuple[PlanSchema, str]:
        """Extract JSON with the hardened extractor and validate the schema.

        Accepts the WORKFLOW section 3 shape and the legacy ``team`` shape
        (``[{agent_type, role_description}]``). Raises ValueError (bad JSON
        or schema) or TypeError (JSON is not an object) on any problem;
        the caller decides retry vs fallback.
        """
        extracted = BaseAgent._extract_json(content or "")
        if extracted is None:
            raise ValueError("no JSON object found in planner reply")
        try:
            data = json.loads(extracted)
        except json.JSONDecodeError as e:
            raise ValueError(f"planner reply is not JSON: {e}") from e
        if not isinstance(data, dict):
            raise TypeError("planner reply JSON is not an object")

        data = dict(data)  # translate legacy shape without mutating the parsed doc
        reasoning = str(data.get("reasoning", ""))
        if "suggested_roles" not in data and isinstance(data.get("team"), list):
            roles = [
                member["agent_type"]
                for member in data["team"]
                if isinstance(member, dict) and member.get("agent_type") in KNOWN_ROLES
            ]
            roles.extend(
                member
                for member in data["team"]
                if isinstance(member, str) and member in KNOWN_ROLES
            )
            if roles:
                data["suggested_roles"] = roles
            # Unknown role names (e.g. a listed synthesizer) are dropped;
            # an empty result below still counts as invalid.

        try:
            schema = PlanSchema.model_validate(data)
        except ValidationError as e:
            raise ValueError(f"plan schema invalid: {e}") from e
        if not schema.suggested_roles:
            raise ValueError("plan suggests no roles")
        return schema, reasoning

    def _apply_capacity(
        self, schema: PlanSchema, reasoning: str, time_budget_minutes: int
    ) -> PlanResult:
        """Clip the validated wish to what the capacity planner allows."""
        tier = self._tier_for_minutes(time_budget_minutes)
        roles = list(schema.suggested_roles)[: TIER_MAX_AGENTS[tier]]
        rounds = min(max(schema.estimated_rounds, MIN_ROUNDS), TIER_MAX_ROUNDS[tier])

        team_plan = self._capacity_plan(schema, roles, rounds, tier)
        capacity_note = ""
        if team_plan is not None:
            if team_plan.feasible and team_plan.agents < len(roles):
                roles = roles[: team_plan.agents]
                rounds = min(rounds, team_plan.rounds)
                capacity_note = f" Capacity trim: {team_plan.explanation}"
            elif not team_plan.feasible:
                capacity_note = f" Capacity warning: {team_plan.explanation}"

        team = [
            {"agent_type": role, "role_description": ROLE_DESCRIPTIONS[role]}
            for role in roles
        ]
        return PlanResult(
            problem_type=schema.problem_type,
            complexity=schema.complexity,
            team_composition=team,
            needs_research=schema.needs_research,
            reasoning=(reasoning + capacity_note).strip(),
            suggested_roles=roles,
            estimated_rounds=rounds,
            needs_code_execution=schema.needs_code_execution,
        )

    def _capacity_plan(
        self,
        schema: PlanSchema,
        roles: list[str],
        rounds: int,
        tier: int,
    ) -> Any:
        """Quota-aware trim via the capacity planner, or None if unavailable.

        Fail-open: routers without a quota snapshot (e.g. test doubles)
        simply keep the tier-clipped team. Never allowed to break planning.
        """
        snapshot = getattr(self.router, "quota_snapshot", None)
        if not callable(snapshot):
            return None
        try:
            keys = [
                KeyBudget(
                    provider=str(entry.get("provider", "unknown")),
                    rpm_limit=entry.get("rpm_limit"),
                    rpd_remaining=entry.get("rpd_remaining"),
                    tpm_limit=entry.get("tpm_limit"),
                    tpd_remaining=entry.get("tpd_remaining"),
                )
                for entry in snapshot()
            ]
            suggestion = PlannerSuggestion(
                roles=tuple(roles),
                complexity=schema.complexity,
                needs_research=schema.needs_research,
                estimated_rounds=rounds,
            )
            return plan_capacity(keys, tier, suggestion)
        except Exception as e:  # noqa: BLE001 — capacity is advisory only
            logger.warning(f"Planner │ Capacity trim skipped: {e}")
            return None

    def _read_capacity(self, time_budget_minutes: int) -> dict[str, object] | None:
        """Ask the router for limiter-based affordable calls (None if unsupported).

        Read-only exposure: the planner logs it and downstream code may trim
        teams later. Never allowed to break planning.
        """
        estimate = getattr(self.router, "capacity_estimate", None)
        if not callable(estimate):
            return None
        try:
            capacity = dict(estimate(time_budget_minutes))
            logger.info(f"Planner │ Quota capacity: {capacity}")
            return capacity
        except Exception as e:  # noqa: BLE001 — capacity is advisory only
            logger.warning(f"Planner │ Capacity estimate unavailable: {e}")
            return None

    def _heuristic_plan(
        self, question: str, time_budget_minutes: int, reason: str
    ) -> PlanResult:
        """Deterministic keyword/length fallback — planning never fails."""
        suggestion = heuristic_suggestion(question)
        tier = self._tier_for_minutes(time_budget_minutes)
        roles = list(suggestion.roles)[: TIER_MAX_AGENTS[tier]]
        rounds = min(suggestion.estimated_rounds, TIER_MAX_ROUNDS[tier])
        team = [
            {"agent_type": role, "role_description": ROLE_DESCRIPTIONS[role]}
            for role in roles
        ]
        problem_type = self._heuristic_problem_type(question)
        return PlanResult(
            problem_type=problem_type,
            complexity=suggestion.complexity,
            team_composition=team,
            needs_research=suggestion.needs_research,
            reasoning=(
                f"Heuristic fallback classifier ({reason}); keywords and length "
                "only, no LLM call."
            ),
            suggested_roles=roles,
            estimated_rounds=rounds,
            needs_code_execution=problem_type in ("coding", "math"),
            fallback_used=True,
        )

    @staticmethod
    def _heuristic_problem_type(question: str) -> str:
        """Keyword sniff for the fallback path (specific phrases first)."""
        from src.orchestration.capacity import RESEARCH_HINTS

        text = (question or "").lower()
        if any(hint in text for hint in _MATH_HINTS):
            return "math"
        if any(hint in text for hint in _CODING_HINTS):
            return "coding"
        if any(hint in text for hint in _MULTISTEP_HINTS):
            return "multi_step"
        if any(hint in text for hint in RESEARCH_HINTS):
            return "research"
        return "general"

    @staticmethod
    def _tier_for_minutes(minutes: int) -> int:
        """Smallest capacity tier covering a time budget (default: largest)."""
        try:
            budget = int(minutes)
        except (TypeError, ValueError):
            budget = 5
        return next((t for t in VALID_TIERS if t >= budget), VALID_TIERS[-1])
