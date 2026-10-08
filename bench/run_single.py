"""Assembly bench — best single free model, one call per question.

Usage:
    python bench/run_single.py [--provider groq] [--model openai/gpt-oss-20b]
        [--run-id single-20260101-120000] [--limit 5]

Default model = the first usable solver candidate in models.yaml catalog
order (fastest/cheapest first by repo convention). Pass --provider/--model
explicitly to benchmark the strongest model instead; --model must be a
catalog id served by the routed provider.

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
    ask_once,
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
from src.providers.router import ModelRouter  # noqa: E402


def build_router() -> ModelRouter:
    """Real router (tests monkeypatch bench.run_single.build_router)."""
    return ModelRouter()


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    """Parse run_single CLI flags."""
    parser = add_common_args(
        argparse.ArgumentParser(description=__doc__)
    )
    parser.add_argument("--provider", default=None)
    parser.add_argument("--model", default=None)
    return parser.parse_args(argv)


async def run_all(args: argparse.Namespace, run_id: str) -> list[BenchResult]:
    """Ask the single model for each pending question. Returns records."""
    router = build_router()
    live = router.get_available_providers()
    print(f"Live providers ({len(live)}): {', '.join(live)}")
    if not live:
        raise SystemExit(
            "ABORT: no live providers — add keys (dev: .env.dev, "
            "desktop: OS keyring) so the key store is non-empty."
        )
    decision = router.route("solver", prefer_provider=args.provider)
    if args.model is not None:
        offered = decision.provider.get_available_models()
        if offered and args.model not in offered:
            raise SystemExit(
                f"ABORT: model {args.model} is not served by "
                f"{decision.provider_name} (offers: {', '.join(offered)})."
            )
        decision.model = args.model
    print(
        f"Single model: {decision.provider_name}/{decision.model} "
        f"(family {decision.family or 'unknown'})"
    )

    questions = load_questions(args.questions)
    store = ResultStore(args.results_dir / f"{run_id}.jsonl")
    pending = remaining_questions(
        questions, store.done_ids(), args.category, args.limit
    )
    print(f"Questions: {len(pending)} pending ({len(questions)} total)")

    policy = QuotaPolicy(
        max_retries=args.max_retries, max_wait_seconds=args.max_wait_seconds
    )
    secrets = load_secrets_best_effort()
    results: list[BenchResult] = []
    for i, item in enumerate(pending):
        started = time.monotonic()
        try:
            outcome = await ask_once(
                decision.provider,
                decision.model,
                build_single_messages(item.question),
                policy=policy,
                timeout_seconds=args.per_question_timeout,
                max_tokens=args.max_tokens,
                secrets=secrets,
            )
        except AbortRunError as exc:
            print(f"ABORT: {exc}")
            break
        elapsed = time.monotonic() - started
        record = BenchResult(
            run_id=run_id,
            mode="single",
            question_id=item.id,
            category=item.category,
            answer_type=item.answer_type,
            difficulty=item.difficulty,
            method={
                "name": "single",
                "provider": decision.provider_name,
                "model": decision.model,
                "family": decision.family,
            },
            answer=outcome.text,
            calls=outcome.calls,
            tokens=outcome.tokens,
            seconds=round(elapsed, 2),
            consensus_score=1.0 if outcome.text else 0.0,
            errors=outcome.errors,
        )
        store.append(record)
        results.append(record)
        status = "ok" if outcome.text else f"errors={outcome.errors}"
        print(f"[{i + 1}/{len(pending)}] {item.id}: {status}")
        logger.info(f"Bench   │ single {item.id}: calls={outcome.calls}")
        if args.sleep_between_seconds > 0 and i < len(pending) - 1:
            await asyncio.sleep(args.sleep_between_seconds)
    return results


def main(argv: list[str] | None = None) -> int:
    """CLI entry: setup, run, summarize. Returns exit code."""
    force_utf8_stdout()
    args = parse_args(argv)
    load_env_file(args.env_file)
    apply_app_mode(args.app_mode)
    run_id = args.run_id or default_run_id("single")
    print(f"Run id: {run_id}")
    started = time.monotonic()
    try:
        results = asyncio.run(run_all(args, run_id))
    except KeyboardInterrupt:
        print(f"\nInterrupted — resume with: python bench/run_single.py --run-id {run_id}")
        return 130
    except SystemExit as exc:
        raise
    print_summary("single", results, time.monotonic() - started)
    if results and all(not r.answer for r in results):
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
