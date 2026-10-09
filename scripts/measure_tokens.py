"""Assembly — one-shot per-call token measurement (5-minute tier).

Runs a single real execution at the 5-minute tier, prints every LLM call
as: stage, role, provider/model, input tokens, output tokens (and
reasoning tokens when the provider reports them), then summarizes the
average and 90th percentile by stage.

Keys come from .env.dev (local only); only provider/model/family NAMES
and token COUNTS are printed — never key values.

Usage:
    python scripts/measure_tokens.py [--question "..."] [--tier 5]
        [--run-id measure-...] [--out results.json]
"""

from __future__ import annotations

import argparse
import asyncio
import json
import math
import sys
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

# Load keys BEFORE any src import creates the Settings singleton:
# .env first (tavily/huggingface/cerebras/openrouter), then .env.dev
# overrides with real dev keys (gemini/groq). os.environ wins over the
# Settings .env file, so the router sees the merged set.
try:
    from dotenv import load_dotenv

    load_dotenv(PROJECT_ROOT / ".env", override=False)
    load_dotenv(PROJECT_ROOT / ".env.dev", override=True)
except ImportError:
    pass

DEFAULT_QUESTION = "Is React better than Vue for a large cybersecurity platform?"


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    """Parse measurement CLI flags."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--question", default=DEFAULT_QUESTION)
    parser.add_argument("--tier", type=int, default=5, choices=(3, 5, 10, 15))
    parser.add_argument("--run-id", default=None)
    parser.add_argument("--out", type=Path, default=None)
    parser.add_argument("--env-file", type=Path, default=None)
    return parser.parse_args(argv)


def percentile(values: list[int], pct: float) -> int:
    """Nearest-rank percentile (pct in 0..100). Returns 0 for empty input."""
    if not values:
        return 0
    ordered = sorted(values)
    rank = max(1, math.ceil(pct / 100.0 * len(ordered)))
    return int(ordered[min(rank - 1, len(ordered) - 1)])


def mean(values: list[int]) -> float:
    """Arithmetic mean (0.0 for empty input)."""
    return sum(values) / len(values) if values else 0.0


def print_per_call(call_log: list[dict]) -> None:
    """Print one line per LLM call (names + counts only)."""
    print("\nPer-call token usage:")
    print(
        f"{'stage':<12} {'round':<5} {'role':<12} "
        f"{'provider/model':<45} {'in':>7} {'out':>7} {'reason':>7} {'total':>7}"
    )
    print("-" * 110)
    for entry in call_log:
        provider_model = f"{entry.get('provider')}/{entry.get('model')}"
        print(
            f"{entry.get('stage', ''):<12} {entry.get('round', 0):<5} "
            f"{entry.get('role', ''):<12} {provider_model[:45]:<45} "
            f"{entry.get('input_tokens', 0):>7} "
            f"{entry.get('output_tokens', 0):>7} "
            f"{entry.get('reasoning_tokens', 0):>7} "
            f"{entry.get('total_tokens', 0):>7}"
        )


def summarize_by_stage(call_log: list[dict]) -> dict[str, dict[str, float]]:
    """Average + p90 total/input/output tokens grouped by stage."""
    by_stage: dict[str, list[dict]] = defaultdict(list)
    for entry in call_log:
        by_stage[str(entry.get("stage", "unknown"))].append(entry)
    summary: dict[str, dict[str, float]] = {}
    print("\nSummary by stage (avg / p90):")
    print(
        f"{'stage':<12} {'n':>3} "
        f"{'avg_in':>8} {'p90_in':>8} "
        f"{'avg_out':>8} {'p90_out':>8} "
        f"{'avg_tot':>8} {'p90_tot':>8} {'avg_reason':>10}"
    )
    print("-" * 100)
    for stage in sorted(by_stage):
        entries = by_stage[stage]
        ins = [int(e.get("input_tokens", 0)) for e in entries]
        outs = [int(e.get("output_tokens", 0)) for e in entries]
        tots = [int(e.get("total_tokens", 0)) for e in entries]
        reasons = [int(e.get("reasoning_tokens", 0)) for e in entries]
        row = {
            "n": len(entries),
            "avg_in": mean(ins),
            "p90_in": percentile(ins, 90),
            "avg_out": mean(outs),
            "p90_out": percentile(outs, 90),
            "avg_total": mean(tots),
            "p90_total": percentile(tots, 90),
            "avg_reason": mean(reasons),
            "max_reason": max(reasons) if reasons else 0,
        }
        summary[stage] = row
        print(
            f"{stage:<12} {len(entries):>3} "
            f"{row['avg_in']:>8.0f} {row['p90_in']:>8} "
            f"{row['avg_out']:>8.0f} {row['p90_out']:>8} "
            f"{row['avg_total']:>8.0f} {row['p90_total']:>8} "
            f"{row['avg_reason']:>10.1f}"
        )
    return summary


async def run_measurement(question: str, tier: int, run_id: str) -> tuple[object, dict]:
    """Run one real orchestrator execution and summarize its call log."""
    from bench.bench_common import apply_app_mode, load_env_file
    from src.orchestration.orchestrator import Orchestrator

    load_env_file(None)
    apply_app_mode(None)
    orchestrator = Orchestrator()
    live = orchestrator.router.get_available_providers()
    print(f"Live providers ({len(live)}): {', '.join(live)}")
    if len(live) < 3:
        raise SystemExit(
            f"ABORT: need >=3 live providers for a real run (have {len(live)}: "
            f"{', '.join(live) or 'none'}). Add keys to .env.dev."
        )
    execution_id = f"{run_id}"
    result = await orchestrator.execute(
        execution_id=execution_id,
        question=question,
        time_budget_minutes=tier,
    )
    summary = summarize_by_stage(list(result.call_log or []))
    return result, summary


def main(argv: list[str] | None = None) -> int:
    """CLI entry: run, print per-call table + summary, optionally save JSON."""
    args = parse_args(argv)
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except (AttributeError, OSError):
        pass
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    run_id = args.run_id or f"measure-5m-{stamp}"
    print(f"Run id: {run_id}")
    print(f"Question: {args.question}")
    print(f"Tier: {args.tier} minutes")
    print(f"Date (UTC): {datetime.now(timezone.utc).isoformat()}")
    try:
        result, summary = asyncio.run(
            run_measurement(args.question, args.tier, run_id)
        )
    except KeyboardInterrupt:
        print("\nInterrupted.")
        return 130
    print_per_call(list(result.call_log or []))
    print(f"\nAnswer status: {result.status} consensus={result.consensus_score:.2f}")
    print(f"Agents: {result.agent_count} debate_rounds={result.debate_rounds}")
    print(f"Total tokens (orchestrator sum, planner excluded): {result.total_tokens}")
    call_total = sum(int(e.get("total_tokens", 0)) for e in (result.call_log or []))
    print(f"Total tokens (call-log sum, planner included): {call_total}")
    reasoning_seen = any(
        int(e.get("reasoning_tokens", 0)) > 0 for e in (result.call_log or [])
    )
    print(f"Reasoning tokens reported by any provider: {reasoning_seen}")
    payload = {
        "run_id": run_id,
        "date_utc": datetime.now(timezone.utc).isoformat(),
        "question": args.question,
        "tier_minutes": args.tier,
        "status": result.status,
        "consensus_score": result.consensus_score,
        "agent_count": result.agent_count,
        "debate_rounds": result.debate_rounds,
        "call_log": list(result.call_log or []),
        "summary_by_stage": summary,
    }
    if args.out is not None:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        print(f"\nSaved measurement JSON to {args.out}")
    else:
        print("\nConfig snippet (paste into src/core/config.py):")
        for stage in sorted(summary):
            row = summary[stage]
            print(
                f"# {stage}: avg_total={row['avg_total']:.0f} "
                f"p90_total={row['p90_total']} n={row['n']}"
            )
        print(f"# source_run_id={run_id}")
    return 0 if result.answer else 1


if __name__ == "__main__":
    raise SystemExit(main())
