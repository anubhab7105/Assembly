"""Assembly bench — offline schedule planner (no LLM calls, no keys).

Estimates how many days N questions at a chosen tier will take from
models.yaml limits, quota_report-style counts, and per-stage token stats.

Usage:
    python bench/plan_schedule.py --questions 40 --tier 5
    python bench/plan_schedule.py --questions 40 --tier 5 --quota-report quota.json
"""

from __future__ import annotations

import argparse
import json
import math
import sys
from pathlib import Path

BENCH_DIR = Path(__file__).resolve().parent
if str(BENCH_DIR.parent) not in sys.path:
    sys.path.insert(0, str(BENCH_DIR.parent))

from src.orchestration.capacity import (
    TIER_MAX_AGENTS,
    cost_of_plan,
    estimated_tokens_median,
)
from src.providers.config import load_models_config


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--questions", type=int, default=40)
    parser.add_argument("--tier", type=int, default=5, choices=[3, 5, 10, 15])
    parser.add_argument("--quota-report", type=Path, default=None)
    parser.add_argument("--models-yaml", type=Path, default=None)
    return parser.parse_args(argv)


def provider_daily_calls(catalog: object) -> dict[str, float]:
    """Affordable calls/day per provider from catalog rpd (0 when unknown)."""
    out: dict[str, float] = {}
    providers = getattr(catalog, "providers", {}) or {}
    for pid, spec in providers.items():
        if not getattr(spec, "enabled", False):
            continue
        total = 0.0
        for model in getattr(spec, "models", []) or []:
            scope = getattr(model, "scope", "model")
            rpd = getattr(getattr(model, "limits", None), "rpd", None)
            if isinstance(rpd, int) and not isinstance(rpd, bool):
                if scope == "account":
                    total = max(total, float(rpd))
                else:
                    total += float(rpd)
        out[str(pid)] = total * 0.7
    return out


def apply_quota_report(
    daily: dict[str, float], report_path: Path | None
) -> dict[str, float]:
    """Reduce daily budgets by quota_report remaining counts (offline file)."""
    if report_path is None:
        return dict(daily)
    try:
        data = json.loads(report_path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return dict(daily)
    remaining = data.get("remaining_by_provider", {}) if isinstance(data, dict) else {}
    out = dict(daily)
    for pid, left in remaining.items():
        try:
            out[str(pid)] = min(float(out.get(pid, 0.0)), max(0.0, float(left)))
        except (TypeError, ValueError):
            continue
    return out


def plan_schedule(
    n_questions: int, tier: int, daily: dict[str, float]
) -> dict[str, object]:
    """Day-by-day schedule: which provider binds and calls/day to allocate."""
    agents = TIER_MAX_AGENTS.get(tier, 4)
    rounds = {3: 1, 5: 2, 10: 3, 15: 4}.get(tier, 2)
    searches = {3: 2, 5: 4, 10: 8, 15: 10}.get(tier, 4)
    calls_per_q = cost_of_plan(agents, rounds, searches)
    tokens_per_q = estimated_tokens_median(agents, rounds, searches)
    total_calls = calls_per_q * max(0, n_questions)
    per_day = sum(v for v in daily.values() if v and v > 0)
    binding = min(daily, key=lambda k: daily[k]) if daily else "none"
    if per_day <= 0:
        days = 0
        schedule: list[dict[str, object]] = []
    else:
        days = math.ceil(total_calls / per_day) if total_calls else 0
        schedule = []
        remaining = total_calls
        for day in range(1, days + 1):
            today = min(per_day, remaining)
            remaining -= today
            schedule.append(
                {"day": day, "calls": int(today), "provider_split": dict(daily)}
            )
    return {
        "n_questions": n_questions,
        "tier": tier,
        "calls_per_question": calls_per_q,
        "tokens_per_question_median": tokens_per_q,
        "total_calls": total_calls,
        "calls_per_day": per_day,
        "binding_provider": binding,
        "days": days,
        "schedule": schedule,
    }


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    catalog = load_models_config(args.models_yaml)
    daily = provider_daily_calls(catalog)
    daily = apply_quota_report(daily, args.quota_report)
    plan = plan_schedule(args.questions, args.tier, daily)
    print(f"Questions: {plan['n_questions']} at tier {plan['tier']}m")
    print(
        f"Calls/question: {plan['calls_per_question']} "
        f"(median tokens {plan['tokens_per_question_median']})"
    )
    print(
        f"Total calls: {plan['total_calls']}; capacity/day: {plan['calls_per_day']:.1f}"
    )
    print(f"Binding provider: {plan['binding_provider']}; days: {plan['days']}")
    for entry in plan["schedule"]:
        split = ", ".join(f"{k}={v:.0f}" for k, v in entry["provider_split"].items())
        print(f"  Day {entry['day']}: {entry['calls']} calls ({split})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
