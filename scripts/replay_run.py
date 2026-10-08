"""Assembly replay mode — re-run a recording offline, no keys, no network.

Usage:
    python scripts/replay_run.py recordings/run-20250101-120000.json
                               [--delay-scale 1.0] [--question "..."] [--budget 3]

This is the demo-day fallback: a previously recorded run plays back
deterministically. delay-scale multiplies recorded latencies
(0 = instant, for fast checks). Question/budget default to the recorded
values; overriding them still replays the same responses in order.

Exit codes: 0 completed (all records consumed), 1 run failed/incomplete.
"""

import argparse
import asyncio
import sys
import time
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.orchestration.orchestrator import Orchestrator
from src.providers.replay_provider import (
    ReplayExhaustedError,
    ReplayRouter,
    load_recording,
)


async def replay_run(
    recording: Path,
    delay_scale: float,
    question: str | None,
    budget: int | None,
) -> int:
    """Replay one recording file end to end. Returns exit code."""
    # Windows consoles default to cp1252, which chokes on model output
    # (e.g. U+2011). Force UTF-8 like src/core/logging_config.py does.
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except (AttributeError, OSError):
        pass
    data = load_recording(recording)
    records = data["records"]
    question = question or data.get("question") or "Replayed question"
    budget = budget if budget is not None else data.get("time_budget_minutes") or 3
    print(f"Replaying {len(records)} recorded call(s) from {recording}")
    print(f"Providers in recording: {sorted({r.get('provider') for r in records})}")

    orch = Orchestrator()
    router = ReplayRouter(records, delay_scale=delay_scale)
    orch.router = router

    async def on_progress(event: dict[str, Any]) -> None:
        if event["event_type"] == "consensus.updated":
            data = event.get("data", {})
            print(
                f"Round {data.get('round', '?')}: "
                f"score={data.get('score', 0.0):.2f} "
                f"decision={data.get('decision', '?')}"
            )

    print(f"\nQuestion: {question}")
    started = time.monotonic()
    try:
        result = await orch.execute(
            execution_id=f"replay-{started:.0f}",
            question=question,
            time_budget_minutes=budget,
            on_progress=on_progress,
        )
    except ReplayExhaustedError as exc:
        print(f"\nREPLAY DIVERGED: {exc}")
        return 1
    elapsed = time.monotonic() - started

    leftover = router.remaining
    if leftover:
        print(f"\nNOTE: {leftover} recorded call(s) unconsumed (run took fewer calls).")
    print(f"\nTotal tokens (replayed): {result.total_tokens}")
    print(f"Wall-clock: {elapsed:.1f}s")
    print(
        f"Status: {result.status} | agents={result.agent_count} "
        f"rounds={result.debate_rounds} providers={result.providers_used}"
    )
    print("\n===== FINAL ANSWER =====")
    print(result.answer)
    print("\n===== SOURCES =====")
    for source in result.sources or []:
        print(f"- {source.get('title', '?')}: {source.get('url', 'n/a')}")
    if not result.sources:
        print("(no sources)")
    return 0 if result.status == "completed" and not leftover else 1


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("recording", type=Path)
    parser.add_argument(
        "--delay-scale",
        type=float,
        default=1.0,
        help="Multiply recorded latencies (0 = instant replay).",
    )
    parser.add_argument("--question", default=None)
    parser.add_argument("--budget", type=int, choices=[3, 5, 10, 15], default=None)
    args = parser.parse_args(argv)
    if args.delay_scale < 0:
        parser.error("--delay-scale must be >= 0")
    return asyncio.run(
        replay_run(args.recording, args.delay_scale, args.question, args.budget)
    )


if __name__ == "__main__":
    raise SystemExit(main())
