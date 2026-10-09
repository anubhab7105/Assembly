"""
Assembly — Capacity-aware planner (docs/WORKFLOW.md section 4).

Decides what team size the current keys and quotas can afford for a
chosen time tier, BEFORE any agent runs. The math is a pure function of
its inputs so it is easy to unit-test with no providers or network:

    for each key:
        calls_now   = min(rpm_limit x minutes_in_budget, rpd_remaining,
                          tpm_limit x minutes / AVG_TOKENS_PER_CALL,
                          tpd_remaining / AVG_TOKENS_PER_CALL)
    total_calls     = sum(calls_now over keys) x 0.7   # 30% safety margin
    cost(plan)      = agents x (1 solve) + rounds x agents x (1 critique)
                      + searches + 1 synthesis + 1 planner
    choose the largest plan with cost(plan) <= total_calls
    if none fits the chosen tier: fall back to the largest feasible
    smaller tier and explain why in plain language.

Time rule: keep ``synth_reserve = max(25 s, 12% of budget)`` for final
synthesis, and never start a round when
``remaining < estimated_round_time + synth_reserve``.

Only quota COUNTS enter this module (limits and remaining calls) — never
raw API keys — so plans cannot leak key material by construction.
"""

from dataclasses import dataclass

# ── Constants ─────────────────────────────────────────────────────────

VALID_TIERS: tuple[int, ...] = (3, 5, 10, 15)

#: Keep a 30% safety margin on quota math (WORKFLOW section 4).
SAFETY_FACTOR: float = 0.7

#: Rough planning estimate of tokens per LLM call (prompt + completion).
#: Not measured — it only keeps token budgets (tpm/tpd) comparable to
#: call counts when deciding whether a plan fits.
AVG_TOKENS_PER_CALL: int = 2000

#: Floor (seconds) for the synthesis time reserve.
SYNTH_RESERVE_MIN_SECONDS: float = 25.0

#: Fraction of the tier budget reserved for final synthesis.
SYNTH_RESERVE_FRACTION: float = 0.12

#: Smallest team that can still cross-examine (solver + critic).
MIN_AGENTS: int = 2

#: Minimum debate/critique passes.
MIN_ROUNDS: int = 1

# Per-tier ceilings. Agent/round ceilings mirror BudgetController so the
# two modules agree; search defaults are the WORKFLOW table midpoints
# (cost = agents + rounds*agents + searches + planner + synthesis lands
# inside the table's approx-call ranges). Replace the time estimates with
# measured numbers after the first benchmark (WORKFLOW section 4).
TIER_MAX_AGENTS: dict[int, int] = {3: 3, 5: 4, 10: 5, 15: 6}
TIER_MAX_ROUNDS: dict[int, int] = {3: 1, 5: 2, 10: 4, 15: 6}
TIER_DEFAULT_ROUNDS: dict[int, int] = {3: 1, 5: 2, 10: 3, 15: 4}
TIER_DEFAULT_SEARCHES: dict[int, int] = {3: 2, 5: 4, 10: 8, 15: 10}
TIER_MAX_SEARCHES: dict[int, int] = {3: 5, 5: 10, 10: 20, 15: 30}

# Time model (seconds). Solves run in parallel, so agent count does not
# multiply wall-clock time; rounds are sequential critique waves.
PLANNER_CALL_SECONDS: float = 15.0
AGENT_CALL_SECONDS: float = 30.0
SEARCH_SECONDS_EACH: float = 5.0
SYNTHESIS_CALL_SECONDS: float = 25.0

#: Question words that suggest live web evidence would help.
RESEARCH_HINTS: tuple[str, ...] = (
    "compare",
    "versus",
    " vs ",
    " vs.",
    "latest",
    "current",
    "research",
    "source",
    "evidence",
    "best",
    "better",
    "review",
    "ecosystem",
    "market",
    "2024",
    "2025",
    "2026",
)


# ── Inputs / output ───────────────────────────────────────────────────


@dataclass(frozen=True)
class KeyBudget:
    """Affordable-call snapshot for ONE quota bucket. Counts only — never keys.

    One entry per bucket (a model-scope model, or a whole account-scope
    pool): buckets with independent windows sum; a shared pool appears
    once and counts once.
    """

    provider: str
    rpm_limit: int | None = None
    rpd_remaining: int | None = None
    tpm_limit: int | None = None
    tpd_remaining: int | None = None


@dataclass(frozen=True)
class PlannerSuggestion:
    """What the planner wants (WORKFLOW section 3 output, trimmed)."""

    roles: tuple[str, ...] = ()
    complexity: str = "medium"
    needs_research: bool = False
    estimated_rounds: int = 1


@dataclass(frozen=True)
class TeamPlan:
    """Capacity verdict for one question + tier."""

    agents: int
    rounds: int
    search_budget: int
    estimated_calls: int
    estimated_seconds: float
    warnings: tuple[str, ...] = ()
    feasible_tier: int = 3
    requested_tier: int = 3
    feasible: bool = True
    downgraded: bool = False
    affordable_calls: int | None = None
    synth_reserve_seconds: float = 25.0
    explanation: str = ""

    def to_dict(self) -> dict:
        """JSON-safe view for the preflight endpoint."""
        return {
            "agents": self.agents,
            "rounds": self.rounds,
            "search_budget": self.search_budget,
            "estimated_calls": self.estimated_calls,
            "estimated_seconds": round(self.estimated_seconds, 1),
            "warnings": list(self.warnings),
            "feasible_tier": self.feasible_tier,
            "requested_tier": self.requested_tier,
            "feasible": self.feasible,
            "downgraded": self.downgraded,
            "affordable_calls": self.affordable_calls,
            "synth_reserve_seconds": round(self.synth_reserve_seconds, 1),
            "explanation": self.explanation,
        }


# ── Pure helpers ──────────────────────────────────────────────────────


def synth_reserve_seconds(budget_minutes: int) -> float:
    """Time kept for final synthesis: max(25 s, 12% of the budget)."""
    return max(SYNTH_RESERVE_MIN_SECONDS, SYNTH_RESERVE_FRACTION * budget_minutes * 60)


def affordable_calls(
    keys: tuple[KeyBudget, ...] | list[KeyBudget], minutes: int
) -> int | None:
    """Quota-affordable calls after the 30% safety margin.

    Per bucket: min(rpm_limit x minutes, rpd_remaining,
    tpm_limit x minutes / AVG_TOKENS_PER_CALL,
    tpd_remaining / AVG_TOKENS_PER_CALL); a side with no known limit is
    ignored. Buckets with NO known limit at all are unlimited-for-planning
    (fail-open, like the router). Returns None when every bucket is
    unlimited, i.e. quota does not constrain the plan. An empty bucket
    list means zero affordable calls.
    """
    if not list(keys):
        return 0
    known: list[int] = []
    for key in keys:
        options: list[int] = []
        if key.rpm_limit is not None:
            options.append(max(0, key.rpm_limit) * max(0, minutes))
        if key.rpd_remaining is not None:
            options.append(max(0, key.rpd_remaining))
        if key.tpm_limit is not None:
            options.append(
                max(0, key.tpm_limit) * max(0, minutes) // AVG_TOKENS_PER_CALL
            )
        if key.tpd_remaining is not None:
            options.append(max(0, key.tpd_remaining) // AVG_TOKENS_PER_CALL)
        if options:
            known.append(min(options))
    if not known:
        return None
    return int(sum(known) * SAFETY_FACTOR)


def cost_of_plan(agents: int, rounds: int, searches: int) -> int:
    """Total LLM/search calls a plan needs (WORKFLOW section 4 formula)."""
    return agents + rounds * agents + searches + 2  # +1 planner, +1 synthesis


def estimated_seconds(
    agents: int,
    rounds: int,
    searches: int,
    avg_call_seconds: float = AGENT_CALL_SECONDS,
) -> float:
    """Wall-clock estimate. Solves are parallel (one wave); rounds stack."""
    _ = agents  # count affects calls, not wall-clock (parallel waves)
    return (
        PLANNER_CALL_SECONDS
        + avg_call_seconds
        + rounds * avg_call_seconds
        + searches * SEARCH_SECONDS_EACH
        + SYNTHESIS_CALL_SECONDS
    )


def can_start_round(
    remaining_seconds: float,
    budget_minutes: int,
    avg_call_seconds: float = AGENT_CALL_SECONDS,
) -> bool:
    """Never start a round without room for the round AND synthesis."""
    return remaining_seconds >= avg_call_seconds + synth_reserve_seconds(budget_minutes)


def heuristic_suggestion(question: str) -> PlannerSuggestion:
    """Cheap planner stand-in for preflight (no LLM call, no quota spent).

    Keyword/length based only: short plain questions read as low
    complexity, research-flavoured or long ones as medium/high.
    The real run still classifies with the LLM planner.
    """
    text = (question or "").lower()
    words = len(text.split())
    needs_research = any(hint in text for hint in RESEARCH_HINTS)
    if words <= 12 and not needs_research:
        return PlannerSuggestion(
            roles=("solver", "critic"),
            complexity="low",
            needs_research=False,
            estimated_rounds=1,
        )
    if words >= 45 or ("controvers" in text and needs_research):
        roles = ("solver", "solver", "researcher", "critic")
        return PlannerSuggestion(
            roles=roles,
            complexity="high",
            needs_research=True,
            estimated_rounds=3,
        )
    roles = (
        ("solver", "solver", "researcher", "critic")
        if needs_research
        else ("solver", "solver", "critic")
    )
    return PlannerSuggestion(
        roles=roles,
        complexity="medium",
        needs_research=needs_research,
        estimated_rounds=2,
    )


# ── Main entry point ──────────────────────────────────────────────────


def _desired_for_tier(suggestion: PlannerSuggestion, tier: int) -> tuple[int, int, int]:
    """Planner wish clipped to one tier's ceilings: (agents, rounds, searches)."""
    if suggestion.roles:
        agents = min(max(len(suggestion.roles), MIN_AGENTS), TIER_MAX_AGENTS[tier])
    elif suggestion.complexity == "low":
        agents = min(MIN_AGENTS, TIER_MAX_AGENTS[tier])
    elif suggestion.complexity == "high":
        agents = TIER_MAX_AGENTS[tier]
    else:
        agents = min(3, TIER_MAX_AGENTS[tier])
    rounds = min(max(suggestion.estimated_rounds, MIN_ROUNDS), TIER_MAX_ROUNDS[tier])
    if suggestion.needs_research:
        searches = min(TIER_DEFAULT_SEARCHES[tier], TIER_MAX_SEARCHES[tier])
    else:
        searches = 0
    return agents, rounds, searches


def _shrink_to_fit(
    agents: int, rounds: int, searches: int, affordable: int | None
) -> tuple[int, int, int]:
    """Trim searches, then rounds, then agents until cost fits (or minimal)."""
    while (
        affordable is not None and cost_of_plan(agents, rounds, searches) > affordable
    ):
        if searches > 0:
            searches = 0
        elif rounds > MIN_ROUNDS:
            rounds -= 1
        elif agents > MIN_AGENTS:
            agents -= 1
        else:
            break
    return agents, rounds, searches


def plan_capacity(
    keys: tuple[KeyBudget, ...] | list[KeyBudget],
    requested_tier: int,
    suggestion: PlannerSuggestion,
    avg_call_seconds: float = AGENT_CALL_SECONDS,
) -> TeamPlan:
    """Pure capacity verdict: the largest plan the quota/time budget affords.

    Each tier has a standard plan (the planner's wish clipped to that
    tier's ceilings). The requested tier wins when its standard cost fits
    the (safety-margined) affordable calls; otherwise the largest smaller
    tier whose standard fits is returned with a human-readable explanation.
    When even the 3-minute standard is too dear, it is trimmed to the
    minimum team — and only if even that cannot fit is the verdict
    infeasible.
    """
    if requested_tier not in VALID_TIERS:
        raise ValueError(
            f"Unknown time tier {requested_tier!r}; expected one of {list(VALID_TIERS)}."
        )
    key_list = list(keys)
    affordable = affordable_calls(key_list, requested_tier)
    reserve = synth_reserve_seconds(requested_tier)
    budget_seconds = requested_tier * 60
    warnings: list[str] = []
    if affordable is None:
        warnings.append(
            "Quota limits are unknown for all keys; planning against the time "
            "budget only (fill models.yaml limits from provider dashboards)."
        )

    full = _desired_for_tier(suggestion, requested_tier)
    for tier in sorted((t for t in VALID_TIERS if t <= requested_tier), reverse=True):
        agents, rounds, searches = _desired_for_tier(suggestion, tier)
        cost = cost_of_plan(agents, rounds, searches)
        seconds = estimated_seconds(agents, rounds, searches, avg_call_seconds)
        if (affordable is None or cost <= affordable) and seconds <= budget_seconds:
            downgraded = tier != requested_tier
            if downgraded:
                warnings.append(
                    f"Requested {requested_tier}-minute tier needs about "
                    f"{cost_of_plan(*full)} calls but only {affordable} are "
                    f"affordable; using the {tier}-minute plan instead."
                )
            explanation = _explain(
                requested_tier,
                tier,
                agents,
                rounds,
                searches,
                cost,
                seconds,
                affordable,
                downgraded,
                reserve,
            )
            return TeamPlan(
                agents=agents,
                rounds=rounds,
                search_budget=searches,
                estimated_calls=cost,
                estimated_seconds=seconds,
                warnings=tuple(warnings),
                feasible_tier=tier,
                requested_tier=requested_tier,
                feasible=True,
                downgraded=downgraded,
                affordable_calls=affordable,
                synth_reserve_seconds=reserve,
                explanation=explanation,
            )

    # No tier standard fits: trim the 3-minute standard to the minimum team.
    agents, rounds, searches = _shrink_to_fit(
        *_desired_for_tier(suggestion, 3), affordable
    )
    cost = cost_of_plan(agents, rounds, searches)
    seconds = estimated_seconds(agents, rounds, searches, avg_call_seconds)
    if (affordable is None or cost <= affordable) and seconds <= budget_seconds:
        warnings.append(
            f"Requested {requested_tier}-minute tier needs about "
            f"{cost_of_plan(*full)} calls but only {affordable} are affordable; "
            "using a trimmed 3-minute team instead."
        )
        if suggestion.needs_research and searches == 0 and affordable is not None:
            warnings.append("Web research dropped: no search budget fits.")
        explanation = _explain(
            requested_tier,
            3,
            agents,
            rounds,
            searches,
            cost,
            seconds,
            affordable,
            True,
            reserve,
        )
        return TeamPlan(
            agents=agents,
            rounds=rounds,
            search_budget=searches,
            estimated_calls=cost,
            estimated_seconds=seconds,
            warnings=tuple(warnings),
            feasible_tier=3,
            requested_tier=requested_tier,
            feasible=True,
            downgraded=True,
            affordable_calls=affordable,
            synth_reserve_seconds=reserve,
            explanation=explanation,
        )

    # Nothing fits, not even the minimal team.
    agents, rounds, searches = MIN_AGENTS, MIN_ROUNDS, 0
    cost = cost_of_plan(agents, rounds, searches)
    seconds = estimated_seconds(agents, rounds, searches, avg_call_seconds)
    reasons: list[str] = []
    if affordable is not None and cost > affordable:
        reasons.append(
            f"even the smallest team needs about {cost} calls "
            f"but only {affordable} are affordable (daily quota exhausted "
            "or rate limits too tight)"
        )
    if seconds > budget_seconds:
        reasons.append("even the smallest team does not fit the time budget")
    detail = " and ".join(reasons) or "no feasible plan"
    explanation = (
        f"Requested {requested_tier}-minute tier is not feasible: {detail}. "
        "Add keys, wait for quota reset, or choose a smaller question."
    )
    warnings.append(explanation)
    return TeamPlan(
        agents=agents,
        rounds=rounds,
        search_budget=searches,
        estimated_calls=cost,
        estimated_seconds=seconds,
        warnings=tuple(warnings),
        feasible_tier=requested_tier,
        requested_tier=requested_tier,
        feasible=False,
        downgraded=False,
        affordable_calls=affordable,
        synth_reserve_seconds=reserve,
        explanation=explanation,
    )


def _explain(
    requested: int,
    feasible_tier: int,
    agents: int,
    rounds: int,
    searches: int,
    cost: int,
    seconds: float,
    affordable: int | None,
    downgraded: bool,
    reserve: float,
) -> str:
    """One human-readable sentence or two about the verdict."""
    quota = f"{affordable}" if affordable is not None else "unknown (time-budget only)"
    if downgraded:
        return (
            f"Requested {requested}-minute tier is not feasible with "
            f"{quota} affordable calls; falling back to the {feasible_tier}-minute "
            f"plan ({agents} agents, {rounds} debate rounds, {searches} searches, "
            f"about {cost} calls in ~{seconds:.0f}s, "
            f"{reserve:.0f}s kept for synthesis)."
        )
    return (
        f"{requested}-minute tier fits: {agents} agents, {rounds} debate rounds, "
        f"{searches} searches (about {cost} calls of {quota} affordable, "
        f"~{seconds:.0f}s with {reserve:.0f}s kept for synthesis)."
    )
