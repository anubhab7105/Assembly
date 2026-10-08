"""Assembly bench — full orchestrator pipeline at configurable tier.

Usage:
    python bench/run_assembly.py [--tier 5] [--run-id assembly-20260101-120000] [--limit 5]

Time budget tiers: 3, 5, 10, 15 minutes (default: 5). The orchestrator
forms a temporary team, runs independent solving → debate → consensus
→ synthesis, and returns a final answer with sources and consensus score.

Writes bench/results/<run_id>.jsonl (resumable via --run-id). Keys come
from the local key store; only provider/model/family names are logged.
"""

from __future__ import annotations

import argparse
import asyncio
import sys
import time
from pathlib import Path

BENCH_DIR = Path(__file__).resolve().parent
if str(BENCH_DIR.parent) not in sys.path:
    sys.path.insert(0, str(BENCH_DIR.parent))

from bench.bench_common import (  # noqa: E402
    AbortRunError,
    BenchResult,
    QuotaPolicy,
    ResultStore,
    add_common_args,
    apply_app_mode,
    build_single_messages,
    default_run_id,
    force_utf8_stdout,
    load_env_file,
    load_questions,
    load_secrets_best_effort,
    print_summary,
    remaining_questions,
)
from src.core.logging_config import logger  # noqa: E402
from src.orchestration.orchestrator import Orchestrator  # noqa: E402


VALID_TIERS = (3, 5, 10, 15)


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    """Parse run_assembly CLI flags."""
    parser = add_common_args(
        argparse.ArgumentParser(description=__doc__)
    )
    parser.add_argument(
        "--tier",
        type=int,
        default=5,
        choices=VALID_TIERS,
        help="Time budget in minutes (3/5/10/15). Default: 5.",
    )
    return parser.parse_args(argv)


async def run_all(args: argparse.Namespace, run_id: str) -> list[BenchResult]:
    """Run the full orchestrator for each pending question. Returns records."""
    orchestrator = Orchestrator()
    router = orchestrator.router
    live = router.get_available_providers()
    print(f"Live providers ({len(live)}): {', '.join(live)}")
    if not live:
        raise SystemExit(
            "ABORT: no live providers — add keys (dev: .env.dev, "
            "desktop: OS keyring) so the key store is non-empty."
        )

    questions = load_questions(args.questions)
    store = ResultStore(args.results_dir / f"{run_id}.jsonl")
    pending = remaining_questions(
        questions, store.done_ids(), args.category, args.limit
    )
    print(f"Questions: {len(pending)} pending ({len(questions)} total)")
    print(f"Tier: {args.tier} minutes")

    # Policy for internal calls (e.g., if orchestrator retries)
    policy = QuotaPolicy(
        max_retries=args.max_retries, max_wait_seconds=args.max_wait_seconds
    )
    secrets = load_secrets_best_effort()
    results: list[BenchResult] = []

    for i, item in enumerate(pending):
        started = time.monotonic()
        errors: list[dict[str, str]] = []
        try:
            execution_id = f"{run_id}-{item.id}"
            result = await orchestrator.execute(
                execution_id=execution_id,
                question=item.question,
                time_budget_minutes=args.tier,
                provider_keys=None,  # Use router's mode key store
            )
            # Orchestrator logs its own errors internally; we record
            # the execution-level status and any exposed warnings.
            if result.status == "failed":
                errors.append(
                    {
                        "phase": "orchestrator",
                        "type": "ExecutionFailed",
                        "message": "Orchestrator returned failed status",
                    }
                )
            elif result.status == "cancelled":
                errors.append(
                    {
                        "phase": "orchestrator",
                        "type": "Cancelled",
                        "message": "Execution was cancelled",
                    }
                )
            elif result.status == "degraded" or result.degraded:
                errors.append(
                    {
                        "phase": "orchestrator",
                        "type": "Degraded",
                        "message": "Execution completed with degraded routing",
                    }
                )
            if result.warnings:
                for w in result.warnings:
                    errors.append(
                        {"phase": "orchestrator", "type": "Warning", "message": w}
                    )
            # Collect agent call/token counts from routing info
            calls = 0
            tokens = 0
            families: list[str] = []
            providers_used: list[str] = []
            for agent_info in (result.routing or []):
                calls += 1  # each agent represents at least one call
                families.append(agent_info.get("family", "unknown"))
                providers_used.append(agent_info.get("provider_name", "unknown"))
            # Total tokens from orchestrator result
            tokens = result.total_tokens

            answer = result.answer or ""
            consensus = round(result.consensus_score, 3) if result.consensus_score is not None else 0.0

        except AbortRunError as exc:
            print(f"ABORT: {exc}")
            break
        except Exception as exc:  # noqa: BLE001 — orchestrator must not crash the bench
            elapsed = time.monotonic() - started
            errors.append(
                {
                    "phase": "orchestrator",
                    "type": type(exc).__name__,
                    "message": str(exc),
                }
            )
            answer = ""
            consensus = 0.0
            calls = 0
            tokens = 0
            providers_used = []
            families = []
        elapsed = time.monotonic() - started

        record = BenchResult(
            run_id=run_id,
            mode="assembly",
            question_id=item.id,
            category=item.category,
            answer_type=item.answer_type,
            difficulty=item.difficulty,
            method={
                "name": "assembly",
                "tier_minutes": args.tier,
                "providers": list(set(providers_used)),
                "families": list(set(families)),
                "agent_count": len(set(families)),
                "debate_rounds": getattr(result, "debate_rounds", 0) if 'result' in locals() else 0,
            },
            answer=answer,
            calls=calls,
            tokens=tokens,
            seconds=round(elapsed, 2),
            consensus_score=consensus,
            errors=errors,
        )
        store.append(record)
        results.append(record)
        status = "ok" if answer else f"errors={errors}"
        print(f"[{i + 1}/{len(pending)}] {item.id}: {status} (consensus={consensus:.0%})")
        logger.info(
            f"Bench   │ assembly {item.id}: consensus={consensus:.3f} "
            f"tokens={tokens} time={elapsed:.1f}s"
        )
        if args.sleep_between_seconds > 0 and i < len(pending) - 1:
            await asyncio.sleep(args.sleep_between_seconds)
    return results


def main(argv: list[str] | None = None) -> int:
    """CLI entry: setup, run, summarize. Returns exit code."""
    force_utf8_stdout()
    args = parse_args(argv)
    load_env_file(args.env_file)
    apply_app_mode(args.app_mode)
    run_id = args.run_id or default_run_id(f"assembly-{args.tier}m")
    print(f"Run id: {run_id}")
    started = time.monotonic()
    try:
        results = asyncio.run(run_all(args, run_id))
    except KeyboardInterrupt:
        print(
            f"\nInterrupted — resume with: "
            f"python bench/run_assembly.py --run-id {run_id}"
        )
        return 130
    except SystemExit as exc:
        raise
    print_summary("assembly", results, time.monotonic() - started)
    if results and all(not r.answer for r in results):
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())