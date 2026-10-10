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

from bench.bench_common import (
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
    resolve_questions_path,
)
from src.core.logging_config import logger
from src.providers.router import ModelRouter


def build_router() -> ModelRouter:
    """Real router (tests monkeypatch bench.run_single.build_router)."""
    return ModelRouter()


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    """Parse run_single CLI flags."""
    parser = add_common_args(argparse.ArgumentParser(description=__doc__))
    parser.add_argument("--provider", default=None)
    parser.add_argument("--model", default=None)
    parser.add_argument(
        "--models",
        default=None,
        help="Comma-separated model ids to pilot (e.g. a,b,c); runs each in turn.",
    )
    return parser.parse_args(argv)


def _pilot_models(args: argparse.Namespace) -> list[str] | None:
    if not getattr(args, "models", None):
        return None
    models = [m.strip() for m in str(args.models).split(",") if m.strip()]
    return models or None


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
    pilot = _pilot_models(args)
    if pilot:
        # Pilot several models in turn (e.g. --models a,b,c): each gets its
        # own sub run id; verification/limit/seed apply per model.
        all_results: list[BenchResult] = []
        for pilot_model in pilot:
            sub_args = argparse.Namespace(**{**vars(args), "model": pilot_model})
            sub_id = f"{run_id}-{pilot_model.replace('/', '_').replace(':', '_')[:40]}"
            print(f"Pilot model: {pilot_model} (run {sub_id})")
            all_results.extend(await _run_one_model(router, sub_args, sub_id))
        return all_results
    decision = router.route("solver", prefer_provider=args.provider)
    if args.model is not None:
        offered = decision.provider.get_available_models()
        if offered and args.model not in offered:
            raise SystemExit(
                f"ABORT: model {args.model} is not served by "
                f"{decision.provider_name} (offers: {', '.join(offered)})."
            )
        decision.model = args.model
    return await _run_with_decision(router, decision, args, run_id)


async def _run_one_model(
    router: object, args: argparse.Namespace, run_id: str
) -> list[BenchResult]:
    decision = router.route("solver", prefer_provider=args.provider)
    if args.model is not None:
        decision.model = str(args.model)
    return await _run_with_decision(router, decision, args, run_id)


async def _run_with_decision(
    router: object, decision: object, args: argparse.Namespace, run_id: str
) -> list[BenchResult]:
    print(
        f"Single model: {decision.provider_name}/{decision.model} "
        f"(family {decision.family or 'unknown'})"
    )

    questions = load_questions(resolve_questions_path(args))
    store = ResultStore(args.results_dir / f"{run_id}.jsonl")
    pending = remaining_questions(
        questions,
        store.done_ids(),
        args.category,
        args.limit,
        getattr(args, "verified_only", True),
        getattr(args, "seed", None),
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
            live=True,
            verification_status=(
                item.verification.status if item.verification else "unverified"
            ),
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
        print(
            f"\nInterrupted — resume with: python bench/run_single.py --run-id {run_id}"
        )
        return 130
    except SystemExit:
        raise
    print_summary("single", results, time.monotonic() - started)
    if results and all(not r.answer for r in results):
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
