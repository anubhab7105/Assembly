"""Assembly bench — full orchestrator pipeline at configurable tier.

Usage:
    python bench/run_assembly.py [--tier 5] [--run-id assembly-20260101-120000] [--limit 5]
        [--pin-team] [--pin-families gemini,qwen,gpt-oss]

Time budget tiers: 3, 5, 10, 15 minutes (default: 5). The orchestrator
forms a temporary team, runs independent solving → debate → consensus
→ synthesis, and returns a final answer with sources and consensus score.

--pin-team fixes model families for the whole run (benchmark integrity):
the first question's answering families become the pins (or --pin-families
when given). Later questions whose answering families fall outside the
pins are NOT silently accepted with substituted families — the runner
sleeps until the quota window resets and retries the same question.
Each result row records which families actually answered (from the
per-call log, successful calls only) plus the routed and pinned sets.

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
    BenchResult,
    ResultStore,
    add_common_args,
    apply_app_mode,
    default_run_id,
    force_utf8_stdout,
    load_env_file,
    load_questions,
    print_summary,
    remaining_questions,
    resolve_questions_path,
)
from src.core.logging_config import logger
from src.orchestration.orchestrator import Orchestrator
from src.providers.router import PinViolationError

VALID_TIERS = (3, 5, 10, 15)

#: Roles a pin set must cover on live providers. Researcher is excluded:
#: whether research runs is question-dependent, so a missing researcher
#: pin is a per-question structural violation, not an up-front abort.
PIN_REQUIRED_ROLES = ("planner", "solver", "critic", "synthesizer")


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    """Parse run_assembly CLI flags."""
    parser = add_common_args(argparse.ArgumentParser(description=__doc__))
    parser.add_argument(
        "--tier",
        type=int,
        default=5,
        choices=VALID_TIERS,
        help="Time budget in minutes (3/5/10/15). Default: 5.",
    )
    parser.add_argument(
        "--pin-team",
        action="store_true",
        help="Pin model families for the whole run; pause-and-retry on "
        "quota exhaustion instead of silently substituting families.",
    )
    parser.add_argument(
        "--pin-families",
        default=None,
        help="Comma-separated families to pin (e.g. gemini,qwen,gpt-oss). "
        "Implies --pin-team. Without it, the first question's answering "
        "families become the pins.",
    )
    parser.add_argument(
        "--pin-max-wait-seconds",
        type=float,
        default=3600.0,
        help="Longest single pause for a quota reset under --pin-team "
        "(default: 3600, max: 86400 = 24h for daily-quota resets). Longer "
        "waits abort the question with an error instead of substituting "
        "families.",
    )
    parser.add_argument(
        "--pin-max-retries",
        type=int,
        default=3,
        help="Pause-and-retry attempts per question under --pin-team (default: 3).",
    )
    return parser.parse_args(argv)


def _answered_families(result: object) -> list[str]:
    """Distinct families with at least one successful LLM call (total > 0).

    Reads the orchestrator call log (stage/role/provider/model/counts);
    falls back to routing info when the log is empty (old replays).
    """
    call_log = list(getattr(result, "call_log", None) or [])
    answered: set[str] = set()
    for entry in call_log:
        if not isinstance(entry, dict):
            continue
        family = str(entry.get("family", "") or "").strip()
        try:
            total = int(entry.get("total_tokens", 0) or 0)
        except (TypeError, ValueError):
            total = 0
        if family and family != "unknown" and total > 0:
            answered.add(family)
    if answered:
        return sorted(answered)
    routed = [
        str(e.get("family", "unknown"))
        for e in (getattr(result, "routing", None) or [])
        if isinstance(e, dict) and str(e.get("family", "")).strip()
    ]
    return sorted(set(routed))


def _routed_families(result: object) -> list[str]:
    """Distinct assigned families from routing info (may include failures)."""
    routed = [
        str(e.get("family", "unknown"))
        for e in (getattr(result, "routing", None) or [])
        if isinstance(e, dict)
    ]
    return sorted(set(routed))


def _has_quota_signal(errors: list[dict[str, str]]) -> bool:
    """True when errors look like rate-limit/quota exhaustion."""
    for error in errors:
        text = f"{error.get('type', '')} {error.get('message', '')}".casefold()
        if any(
            marker in text
            for marker in (
                "ratelimit",
                "rate-limit",
                "rate limit",
                "quota",
                "429",
                "cooling",
                "cooldown",
                "exhausted",
            )
        ):
            return True
    return False


def _quota_wait_seconds(router: object) -> float:
    """Longest cooling window across live keys (0 when none cooling)."""
    wait, _providers = _quota_wait(router)
    return wait


def _cooling_providers(router: object) -> list[str]:
    """Live providers currently cooling down (quota reset pending)."""
    _wait, providers = _quota_wait(router)
    return providers


def _quota_wait(router: object) -> tuple[float, list[str]]:
    """(longest cooldown seconds, providers cooling) across live keys."""
    snapshot = getattr(router, "quota_snapshot", None)
    if not callable(snapshot):
        return 0.0, []
    try:
        entries = snapshot()
    except Exception:  # noqa: BLE001 — quota must never break the bench
        return 0.0, []
    waits: list[float] = []
    cooling: list[str] = []
    for entry in entries or []:
        if not isinstance(entry, dict):
            continue
        try:
            seconds = float(entry.get("cooldown_seconds") or 0.0)
        except (TypeError, ValueError):
            continue
        waits.append(seconds)
        if seconds > 0:
            cooling.append(str(entry.get("provider", "unknown")))
    if not waits:
        return 0.0, []
    return max(waits), sorted(set(cooling))


#: Longest --pin-max-wait-seconds pause: 24h covers daily-quota resets.
PIN_MAX_WAIT_CAP_SECONDS: float = 86400.0


def _check_pin_wait(max_wait: float) -> float:
    """Validate --pin-max-wait-seconds (0 < w <= 24h); SystemExit otherwise."""
    try:
        wait = float(max_wait)
    except (TypeError, ValueError):
        raise SystemExit(
            "ABORT: --pin-max-wait-seconds must be a number of seconds."
        ) from None
    if not 0 < wait <= PIN_MAX_WAIT_CAP_SECONDS:
        raise SystemExit(
            "ABORT: --pin-max-wait-seconds must satisfy 0 < w <= 86400 "
            f"(24h); got {max_wait!r}."
        )
    return wait


def _pin_role_coverage(router: object) -> dict[str, list[str]]:
    """Pinned-role feasibility input: role → families on live providers.

    Reads the router catalog restricted to live (keyed, enabled,
    limits-filled) providers. Pure read — no LLM calls, no quota spent.
    """
    live = set(router.get_available_providers())
    coverage: dict[str, set[str]] = {}
    providers = getattr(getattr(router, "config", None), "providers", {}) or {}
    for provider_id, spec in providers.items():
        if provider_id not in live:
            continue
        for model in getattr(spec, "models", []) or []:
            for role in getattr(model, "roles", []) or []:
                coverage.setdefault(str(role), set()).add(str(model.family))
    return {role: sorted(fams) for role, fams in coverage.items()}


def validate_pins(router: object, pinned: list[str]) -> None:
    """Abort fast when pins cannot serve a required role (SystemExit).

    Prints which roles are covered by which pinned families so a bad
    --pin-families value fails before the first LLM call instead of
    burning retries. Researcher gaps warn only (question-dependent).
    Raises SystemExit with an actionable message on a required-role gap.
    """
    coverage = _pin_role_coverage(router)
    pinned_set = set(pinned)
    gaps: list[str] = []
    for role in PIN_REQUIRED_ROLES:
        offering = [fam for fam in coverage.get(role, []) if fam in pinned_set]
        if not offering:
            available = ", ".join(coverage.get(role, [])) or "none live"
            gaps.append(f"{role}: pinned families offer none (live: {available})")
    researcher_offering = [
        fam for fam in coverage.get("researcher", []) if fam in pinned_set
    ]
    if not researcher_offering:
        available = ", ".join(coverage.get("researcher", [])) or "none live"
        print(
            f"NOTE: pins lack a researcher family (live: {available}) — "
            "questions needing research will abort fast with PinViolation "
            "instead of substituting."
        )
    if gaps:
        raise SystemExit(
            "ABORT: --pin-families "
            f"({', '.join(pinned)}) cannot serve: "
            + "; ".join(gaps)
            + ". Add families covering those roles (note: the critic needs "
            "a family outside the solver families)."
        )
    print(
        "Pins feasible: "
        + ", ".join(
            f"{role}=[{', '.join(f for f in coverage.get(role, []) if f in pinned_set)}]"
            for role in PIN_REQUIRED_ROLES
        )
    )


def _pin_wait_line(providers: list[str], wait: float) -> str:
    """Human-readable pause line naming who is cooling and until when.

    Always renders as "waiting for <provider> quota until <time>" (UTC)
    so operators can see exactly which quota window gates the retry.
    Pure helper: unit-tested without sleeping.
    """
    from datetime import datetime, timedelta, timezone

    who = ", ".join(providers) if providers else "quota"
    resume_at = datetime.now(timezone.utc) + timedelta(seconds=max(0.0, wait))
    return f"waiting for {who} quota until {resume_at.isoformat(timespec='seconds')}"


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
    print(f"Tier: {args.tier} minutes")

    pin_team = bool(
        getattr(args, "pin_team", False) or getattr(args, "pin_families", None)
    )
    pinned: list[str] | None = None
    if getattr(args, "pin_families", None):
        pinned = sorted(
            {part.strip() for part in str(args.pin_families).split(",") if part.strip()}
        )
        if not pinned:
            raise SystemExit("ABORT: --pin-families parsed to no families.")
        print(f"Pinned families (from --pin-families): {', '.join(pinned)}")
    elif pin_team:
        print("Pinned families: auto (first question's answering families)")
    max_wait = _check_pin_wait(getattr(args, "pin_max_wait_seconds", 3600.0))
    max_retries = int(getattr(args, "pin_max_retries", 3) or 0)
    if pin_team and pinned:
        validate_pins(router, pinned)

    results: list[BenchResult] = []

    for i, item in enumerate(pending):
        started = time.monotonic()
        errors: list[dict[str, str]] = []
        answer = ""
        consensus = 0.0
        calls = 0
        tokens = 0
        providers_used: list[str] = []
        routed: list[str] = []
        answered: list[str] = []
        debate_rounds = 0
        team_size = 0
        attempts = 0
        while True:
            attempts += 1
            errors = []
            answer = ""
            consensus = 0.0
            calls = 0
            tokens = 0
            providers_used = []
            routed = []
            answered = []
            debate_rounds = 0
            team_size = 0
            try:
                execution_id = f"{run_id}-{item.id}"
                if attempts > 1:
                    execution_id = f"{execution_id}-retry{attempts}"
                result = await orchestrator.execute(
                    execution_id=execution_id,
                    question=item.question,
                    time_budget_minutes=args.tier,
                    provider_keys=None,  # Use router's mode key store
                    allowed_families=pinned if pin_team else None,
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
                # Answered families (successful calls only) + routed set.
                answered = _answered_families(result)
                routed = _routed_families(result)
                routing = list(result.routing or [])
                team_size = len(routing)
                for agent_info in routing:
                    providers_used.append(agent_info.get("provider_name", "unknown"))
                # Total LLM calls: per-call log when available (planner +
                # debate rounds make calls > agents); fall back to agents.
                try:
                    logged_calls = len(list(getattr(result, "call_log", None) or []))
                except TypeError:
                    logged_calls = 0
                calls = max(team_size, logged_calls)
                # Total tokens from orchestrator result
                tokens = result.total_tokens

                answer = result.answer or ""
                consensus = (
                    round(result.consensus_score, 3)
                    if result.consensus_score is not None
                    else 0.0
                )
                debate_rounds = result.debate_rounds

            except PinViolationError as exc:
                # Structural pin gap (pins cannot serve a role): no sleep
                # will fix it — record and move on.
                errors.append(
                    {
                        "phase": "pin-team",
                        "type": "PinViolation",
                        "message": str(exc),
                    }
                )
                answer = ""
                consensus = 0.0
                calls = 0
                tokens = 0
                providers_used = []
                routed = []
                answered = []
                debate_rounds = 0
                team_size = 0
            except Exception as exc:  # noqa: BLE001 — orchestrator must not crash the bench
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
                routed = []
                answered = []
                debate_rounds = 0
                team_size = 0
            if not pin_team:
                break
            if pinned is None:
                pinned = list(answered or routed)
                if pinned:
                    print(f"Pinned families (from {item.id}): {', '.join(pinned)}")
                break
            outside = [fam for fam in answered if fam not in pinned]
            missing_pinned = [
                fam for fam in set(routed) & set(pinned) if fam not in answered
            ]
            quota_hit = _has_quota_signal(errors)
            needs_retry = bool(outside) or (bool(missing_pinned) and quota_hit)
            if not needs_retry:
                break
            if attempts > max_retries:
                errors.append(
                    {
                        "phase": "pin-team",
                        "type": "PinViolation",
                        "message": (
                            f"answering families {sorted(answered)} fall outside "
                            f"pins {pinned} (routed {sorted(routed)}); "
                            f"max retries ({max_retries}) hit — recording "
                            "actual families instead of substituting silently."
                        ),
                    }
                )
                break
            wait = _quota_wait_seconds(router)
            if wait <= 0:
                wait = 60.0
            if wait > max_wait:
                errors.append(
                    {
                        "phase": "pin-team",
                        "type": "PinViolation",
                        "message": (
                            f"answering families {sorted(answered)} fall outside "
                            f"pins {pinned}; quota reset needs {wait:.0f}s > "
                            f"--pin-max-wait-seconds {max_wait:.0f}s — recording "
                            "actual families instead of waiting."
                        ),
                    }
                )
                break
            wait_line = _pin_wait_line(_cooling_providers(router), wait)
            print(
                f"PIN VIOLATION on {item.id} (attempt {attempts}): answered "
                f"{sorted(answered)} outside pins {pinned} "
                f"(routed {sorted(routed)}); {wait_line} instead of "
                "substituting."
            )
            logger.warning(
                f"Bench   │ pin-team violation on {item.id}: answered "
                f"{sorted(answered)} vs pins {pinned}; {wait_line} "
                f"(attempt {attempts})"
            )
            await asyncio.sleep(wait)
        elapsed = time.monotonic() - started

        method: dict[str, object] = {
            "name": "assembly",
            "tier_minutes": args.tier,
            "providers": sorted(set(providers_used)),
            "families": answered or sorted(set(routed)),
            "answered_families": answered,
            "routed_families": sorted(set(routed)),
            "agent_count": team_size,
            "debate_rounds": debate_rounds,
        }
        record = BenchResult(
            run_id=run_id,
            mode="assembly",
            question_id=item.id,
            category=item.category,
            answer_type=item.answer_type,
            difficulty=item.difficulty,
            method=method,
            answer=answer,
            calls=calls,
            tokens=tokens,
            seconds=round(elapsed, 2),
            consensus_score=consensus,
            errors=errors,
            live=True,
            verification_status=(
                item.verification.status if item.verification else "unverified"
            ),
        )
        if pin_team and pinned is not None:
            record.method["pinned_families"] = list(pinned)
            record.method["pin_retries"] = attempts - 1
        store.append(record)
        results.append(record)
        status = "ok" if answer else f"errors={errors}"
        print(
            f"[{i + 1}/{len(pending)}] {item.id}: {status} (consensus={consensus:.0%})"
        )
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
    except SystemExit:
        raise
    print_summary("assembly", results, time.monotonic() - started)
    if results and all(not r.answer for r in results):
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
