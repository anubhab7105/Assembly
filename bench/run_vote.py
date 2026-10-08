"""Assembly bench — 3-model vote across distinct families, one call each.

Usage:
    python bench/run_vote.py [--run-id vote-20260101-120000] [--limit 5]

Combination rule (documented here and in bench/README.md):
1. Ask 3 solvers routed to 3 DISTINCT families (enforced by
   ModelRouter.route_team). If the catalog cannot supply 3 families, the
   run proceeds with what exists and records a warning in every method.
2. MAJORITY: normalized answers (strip/casefold/collapse whitespace) with
   2+ of 3 votes win. consensus_score = matching votes / successful votes.
3. TIE (all three differ): JUDGE-PICK — the first voter is asked once more
   to choose between the candidates. A judge reply matching a candidate
   (normalized) selects it; otherwise the judge's raw reply is the answer.
   consensus_score = votes matching the final answer / successful votes
   (1/3 when the judge writes something new).

Writes bench/results/<run_id>.jsonl (resumable via --run-id). Keys come
from the local key store; only provider/model/family names are logged.
"""

from __future__ import annotations

import argparse
import asyncio
import sys
import time
from pathlib import Path
from typing import Any

BENCH_DIR = Path(__file__).resolve().parent
if str(BENCH_DIR.parent) not in sys.path:
    sys.path.insert(0, str(BENCH_DIR.parent))

from bench.bench_common import (  # noqa: E402
    AbortRunError,
    AskOutcome,
    BenchResult,
    QuotaPolicy,
    ResultStore,
    add_common_args,
    apply_app_mode,
    ask_once,
    build_judge_messages,
    build_single_messages,
    default_run_id,
    force_utf8_stdout,
    load_env_file,
    load_questions,
    load_secrets_best_effort,
    majority_winner,
    match_candidate,
    normalize_text,
    print_summary,
    remaining_questions,
)
from src.core.logging_config import logger  # noqa: E402
from src.providers.router import ModelRouter, RoutingDecision  # noqa: E402

VOTER_COUNT = 3


def build_router() -> ModelRouter:
    """Real router (tests monkeypatch bench.run_vote.build_router)."""
    return ModelRouter()


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    """Parse run_vote CLI flags."""
    return add_common_args(argparse.ArgumentParser(description=__doc__)).parse_args(
        argv
    )


def _vote_entry(
    decision: RoutingDecision, outcome: AskOutcome
) -> dict[str, Any]:
    """Names-only vote record for one voter."""
    return {
        "provider": decision.provider_name,
        "model": decision.model,
        "family": decision.family,
        "answer": outcome.text,
        "calls": outcome.calls,
        "tokens": outcome.tokens,
        "errors": outcome.errors,
    }


async def _judge_pick(
    judge: RoutingDecision,
    question: str,
    candidates: list[str],
    policy: QuotaPolicy,
    args: argparse.Namespace,
    secrets: list[str],
) -> tuple[str, AskOutcome]:
    """Ask the first voter to choose; match reply to a candidate."""
    outcome = await ask_once(
        judge.provider,
        judge.model,
        build_judge_messages(question, candidates),
        policy=policy,
        timeout_seconds=args.per_question_timeout,
        max_tokens=args.max_tokens,
        secrets=secrets,
    )
    if outcome.text:
        picked = match_candidate(outcome.text, candidates)
        return (picked if picked is not None else outcome.text), outcome
    return candidates[0], outcome


async def run_all(args: argparse.Namespace, run_id: str) -> list[BenchResult]:
    """Ask 3 family-distinct voters per pending question. Returns records."""
    router = build_router()
    live = router.get_available_providers()
    print(f"Live providers ({len(live)}): {', '.join(live)}")
    team = [{"agent_type": "solver", "role_description": "Benchmark voter"}] * VOTER_COUNT
    routing = router.route_team(team)
    voters: list[RoutingDecision] = list(routing.decisions[:VOTER_COUNT])
    families = [v.family for v in voters]
    print(
        "Voters: "
        + ", ".join(f"{v.provider_name}/{v.model} ({v.family})" for v in voters)
    )
    warnings: list[str] = list(routing.warnings)
    if len(set(families)) < VOTER_COUNT:
        warnings.append(
            f"only {len(set(families))} distinct families for "
            f"{VOTER_COUNT} voters: votes are not independent"
        )
    for warning in warnings:
        print(f"WARNING: {warning}")

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
        errors: list[dict[str, str]] = []
        votes: list[dict[str, Any]] = []
        judge_info: dict[str, Any] = {"used": False}
        try:
            for voter in voters:
                outcome = await ask_once(
                    voter.provider,
                    voter.model,
                    build_single_messages(item.question),
                    policy=policy,
                    timeout_seconds=args.per_question_timeout,
                    max_tokens=args.max_tokens,
                    secrets=secrets,
                )
                votes.append(_vote_entry(voter, outcome))
                errors.extend(outcome.errors)
            successful = [v["answer"] for v in votes if v["answer"]]
            winner, top = majority_winner(successful)
            if winner is not None:
                final, rule = winner, f"majority {top}/3"
            elif successful:
                judge = voters[0]
                final, judge_outcome = await _judge_pick(
                    judge, item.question, successful, policy, args, secrets
                )
                errors.extend(judge_outcome.errors)
                judge_info = {
                    "used": True,
                    "provider": judge.provider_name,
                    "model": judge.model,
                    "family": judge.family,
                    "calls": judge_outcome.calls,
                    "tokens": judge_outcome.tokens,
                }
                rule = "judge-pick by voter 1"
            else:
                final, rule = "", "no successful votes"
            match_count = (
                sum(1 for a in successful if normalize_text(a) == normalize_text(final))
                if final and successful
                else 0
            )
            consensus = round(match_count / len(successful), 3) if successful else 0.0
        except AbortRunError as exc:
            print(f"ABORT: {exc}")
            break
        elapsed = time.monotonic() - started
        calls = sum(v["calls"] for v in votes) + judge_info.get("calls", 0)
        tokens = sum(v["tokens"] for v in votes) + judge_info.get("tokens", 0)
        record = BenchResult(
            run_id=run_id,
            mode="vote",
            question_id=item.id,
            category=item.category,
            answer_type=item.answer_type,
            difficulty=item.difficulty,
            method={
                "name": "vote",
                "rule": rule,
                "votes": votes,
                "judge": judge_info,
                "warnings": warnings,
            },
            answer=final,
            calls=calls,
            tokens=tokens,
            seconds=round(elapsed, 2),
            consensus_score=consensus,
            errors=errors,
        )
        store.append(record)
        results.append(record)
        print(f"[{i + 1}/{len(pending)}] {item.id}: {rule} consensus={consensus}")
        logger.info(f"Bench   │ vote {item.id}: {rule}")
        if args.sleep_between_seconds > 0 and i < len(pending) - 1:
            await asyncio.sleep(args.sleep_between_seconds)
    return results


def main(argv: list[str] | None = None) -> int:
    """CLI entry: setup, run, summarize. Returns exit code."""
    force_utf8_stdout()
    args = parse_args(argv)
    load_env_file(args.env_file)
    apply_app_mode(args.app_mode)
    run_id = args.run_id or default_run_id("vote")
    print(f"Run id: {run_id}")
    started = time.monotonic()
    try:
        results = asyncio.run(run_all(args, run_id))
    except KeyboardInterrupt:
        print(f"\nInterrupted — resume with: python bench/run_vote.py --run-id {run_id}")
        return 130
    print_summary("vote", results, time.monotonic() - started)
    if results and all(not r.answer for r in results):
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
