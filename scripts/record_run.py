"""Assembly record mode — run once with real keys, save every model call.

Usage:
    python scripts/record_run.py [--question "..."] [--budget 3]
                                 [--out recordings/run-20250101-120000.json]

Keys:   loaded from .env.dev (git-ignored). Recordings hold provider/model
        names, messages, responses, and token counts — NEVER api keys.
Output: a versioned JSON recording playable with scripts/replay_run.py
        (demo-day fallback) or tests/test_replay.py (regression).
"""

import argparse
import asyncio
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

# Load .env.dev into os.environ BEFORE importing src.* (settings reads env at import).
from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parent.parent
load_dotenv(PROJECT_ROOT / ".env.dev", override=True)
sys.path.insert(0, str(PROJECT_ROOT))

from src.orchestration.orchestrator import Orchestrator
from src.providers.replay_provider import RecordingRouter

DEFAULT_QUESTION = (
    "Is React better than Vue for a large cybersecurity platform? "
    "Compare ecosystem, performance, state management at scale, and hiring."
)


def default_out_path() -> Path:
    """Timestamped default so runs never overwrite each other."""
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    return PROJECT_ROOT / "recordings" / f"run-{stamp}.json"


async def record_run(question: str, budget: int, out: Path) -> int:
    """Execute once with live providers while recording. Returns exit code."""
    orch = Orchestrator()
    live = orch.router.get_available_providers()
    print(f"Live providers ({len(live)}): {', '.join(live)}")
    if not live:
        print("ABORT: no live providers — add keys to .env.dev first.")
        return 2

    recorder = RecordingRouter(orch.router)
    orch.router = recorder

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
    result = await orch.execute(
        execution_id=f"record-{started:.0f}",
        question=question,
        time_budget_minutes=budget,
        on_progress=on_progress,
    )
    elapsed = time.monotonic() - started

    saved = recorder.save(out, question=question, time_budget_minutes=budget)
    print(f"\nRecorded calls: {len(recorder.records)} -> {saved}")
    print(f"Total tokens: {result.total_tokens}")
    print(f"Wall-clock: {elapsed:.1f}s (budget {budget * 60}s)")
    print(
        f"Status: {result.status} | agents={result.agent_count} "
        f"rounds={result.debate_rounds} providers={result.providers_used}"
    )
    print("\n===== FINAL ANSWER (preview) =====")
    print(result.answer[:2000])
    return 0 if result.status == "completed" else 1


def main(argv: list[str] | None = None) -> int:
    # Windows consoles default to cp1252, which chokes on model output
    # (e.g. U+2011). Force UTF-8 like src/core/logging_config.py does.
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except (AttributeError, OSError):
        pass
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--question", default=DEFAULT_QUESTION)
    parser.add_argument("--budget", type=int, choices=[3, 5, 10, 15], default=3)
    parser.add_argument("--out", type=Path, default=None)
    args = parser.parse_args(argv)
    out = args.out or default_out_path()
    return asyncio.run(record_run(args.question, args.budget, out))


if __name__ == "__main__":
    raise SystemExit(main())
