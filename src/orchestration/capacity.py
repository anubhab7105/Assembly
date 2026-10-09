"""
Assembly — Capacity-aware planner (docs/WORKFLOW.md section 4).

Decides what team size the current keys and quotas can afford for a
chosen time tier, BEFORE any agent runs. The math is a pure function of
its inputs so it is easy to unit-test with no providers or network:

    for each key:
        calls_now   = min(rpm_limit x minutes_in_budget, rpd_remaining,
                          tpm_limit x minutes / tpm_tokens_per_call(),
                          tpd_remaining / tpm_tokens_per_call())
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

#: Tokens-per-call divisor converting tpm/tpd token windows into call
#: counts. Measured, not guessed: the max of the per-stage Settings avgs
#: (planner/solve/debate/adversarial/synthesis, source run id/date in
#: config) — max, so token windows bind conservatively. Recomputed from
#: Settings on every call so re-measurement propagates without code edits.
#: Replaces the old flat AVG_TOKENS_PER_CALL=2000 guess at rebase time.
def tpm_tokens_per_call() -> int:
    """Conservative measured tokens/call divisor for tpm/tpd math."""
    try:
        from src.core.config import settings

        stages = (
            settings.tokens_planner_avg,
            settings.tokens_solve_avg,
            settings.tokens_debate_avg,
            settings.tokens_adversarial_avg,
            settings.tokens_synthesis_avg,
        )
        return max(1, max(int(v or 0) for v in stages))
    except (AttributeError, TypeError, ValueError):
        return 2000


#: Back-compat alias: prefer tpm_tokens_per_call() (measured). Kept so
#: any out-of-tree references keep working during the migration window.
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
#
# Rounds are a CEILING, not a fixed count: the consensus engine stops early
# via FINALIZE as soon as score >= threshold with low new-info and no
# critical contradiction. Extra tier time funds more DEBATE/ADVERSARIAL and
# research/verification rounds only when consensus is NOT reached — a tier
# that converges in 1 round still finalizes in 1 round.
TIER_MAX_AGENTS: dict[int, int] = {3: 3, 5: 4, 10: 5, 15: 6}
TIER_MAX_ROUNDS: dict[int, int] = {3: 1, 5: 3, 10: 5, 15: 8}
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
    estimated_tokens_median: int = 0
    estimated_tokens_worst: int = 0

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
            "estimated_tokens_median": self.estimated_tokens_median,
            "estimated_tokens_worst": self.estimated_tokens_worst,
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
    tpm_limit x minutes / tpm_tokens_per_call(),
    tpd_remaining / tpm_tokens_per_call()); a side with no known limit is
    ignored. Buckets with NO known limit at all are unlimited-for-planning
    (fail-open, like the router). Returns None when every bucket is
    unlimited, i.e. quota does not constrain the plan. An empty bucket
    list means zero affordable calls.
    """
    if not list(keys):
        return 0
    divisor = tpm_tokens_per_call()
    known: list[int] = []
    for key in keys:
        options: list[int] = []
        if key.rpm_limit is not None:
            options.append(max(0, key.rpm_limit) * max(0, minutes))
        if key.rpd_remaining is not None:
            options.append(max(0, key.rpd_remaining))
        if key.tpm_limit is not None:
            options.append(max(0, key.tpm_limit) * max(0, minutes) // divisor)
        if key.tpd_remaining is not None:
            options.append(max(0, key.tpd_remaining) // divisor)
        if options:
            known.append(min(options))
    if not known:
        return None
    return int(sum(known) * SAFETY_FACTOR)


def cost_of_plan(agents: int, rounds: int, searches: int) -> int:
    """Total LLM/search calls a plan needs (WORKFLOW section 4 formula)."""
    return agents + rounds * agents + searches + 2  # +1 planner, +1 synthesis


def _stage_tokens(stage: str, worst: bool) -> int:
    """Measured tokens/call for one stage (avg, or p90 when worst=True).

    Reads the Settings token stats (source run id/date recorded there).
    Fail-open: unknown stages or unreadable config read as 0 so the
    estimate degrades instead of breaking planning.
    """
    try:
        from src.core.config import settings

        field = f"tokens_{stage}_{'p90' if worst else 'avg'}"
        return max(0, int(getattr(settings, field, 0) or 0))
    except (AttributeError, TypeError, ValueError):
        return 0


def estimated_tokens_median(agents: int, rounds: int, searches: int) -> int:
    """Expected tokens for a plan at measured avg rates (planned rounds).

    Searches are not LLM calls and carry no model tokens. The single
    adversarial strike is a sometimes-cost: median plans exclude it.
    """
    _ = searches
    return (
        _stage_tokens("planner", False)
        + max(0, agents) * _stage_tokens("solve", False)
        + max(0, agents) * max(0, rounds) * _stage_tokens("debate", False)
        + _stage_tokens("synthesis", False)
    )


def estimated_tokens_worst(agents: int, ceiling_rounds: int, searches: int) -> int:
    """Worst-case tokens for a plan at p90 rates and ceiling rounds.

    Includes one adversarial strike (a critic call at debate p90 rates):
    worst case assumes consensus never lands early.
    """
    _ = searches
    return (
        _stage_tokens("planner", True)
        + max(0, agents) * _stage_tokens("solve", True)
        + max(0, agents) * max(0, ceiling_rounds) * _stage_tokens("debate", True)
        + _stage_tokens("adversarial", True)
        + _stage_tokens("synthesis", True)
    )


def token_cap_for_tier(tier: int) -> int | None:
    """Max execution tokens for a tier (None only if unreadable).

    Single source is BudgetController.token_cap_for_tier; this wrapper
    keeps capacity importable even if that lookup ever fails.
    """
    try:
        from src.orchestration.budget_controller import BudgetController

        return int(BudgetController.token_cap_for_tier(tier))
    except (AttributeError, TypeError, ValueError, ImportError):
        return None


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
        tokens_median = estimated_tokens_median(agents, rounds, searches)
        tokens_worst = estimated_tokens_worst(agents, TIER_MAX_ROUNDS[tier], searches)
        cap = token_cap_for_tier(tier)
        tokens_fit = cap is None or tokens_worst <= cap
        if (
            (affordable is None or cost <= affordable)
            and seconds <= budget_seconds
            and tokens_fit
        ):
            downgraded = tier != requested_tier
            if downgraded:
                full_cost = cost_of_plan(*full)
                full_worst = estimated_tokens_worst(
                    full[0], TIER_MAX_ROUNDS[requested_tier], full[2]
                )
                full_cap = token_cap_for_tier(requested_tier)
                reasons: list[str] = []
                if affordable is not None and full_cost > affordable:
                    reasons.append(
                        f"about {full_cost} calls but only {affordable} are affordable"
                    )
                if full_cap is not None and full_worst > full_cap:
                    reasons.append(
                        f"about {full_worst} worst-case tokens (p90) over the "
                        f"{full_cap} token cap"
                    )
                detail = "; ".join(reasons) or (
                    f"about {full_cost} calls do not fit {affordable} affordable"
                )
                warnings.append(
                    f"Requested {requested_tier}-minute tier needs {detail}; "
                    f"using the {tier}-minute plan instead."
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
                estimated_tokens_median=tokens_median,
                estimated_tokens_worst=tokens_worst,
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
        trimmed_worst = estimated_tokens_worst(agents, TIER_MAX_ROUNDS[3], searches)
        trimmed_cap = token_cap_for_tier(3)
        if trimmed_cap is not None and trimmed_worst > trimmed_cap:
            warnings.append(
                f"Even the trimmed team estimates about {trimmed_worst} "
                f"worst-case tokens (p90) over the {trimmed_cap} token cap; "
                "it may hit the execution token budget if consensus never "
                "lands early."
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
            estimated_tokens_median=estimated_tokens_median(agents, rounds, searches),
            estimated_tokens_worst=estimated_tokens_worst(
                agents, TIER_MAX_ROUNDS[3], searches
            ),
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
