"""Assembly smoke test — one real-key execution, 3-minute budget.

Usage:  python scripts/smoke.py
Keys:   loaded from .env.dev (git-ignored). This script NEVER prints keys —
        only provider/model names, counts, scores, and the final answer.
"""

import asyncio
import sys
import time
from pathlib import Path
from typing import Any

# Load .env.dev into os.environ BEFORE importing src.* (settings reads env at import).
from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parent.parent
load_dotenv(PROJECT_ROOT / ".env.dev", override=True)
sys.path.insert(0, str(PROJECT_ROOT))

from src.orchestration.orchestrator import Orchestrator

QUESTION = (
    "Is React better than Vue for a large cybersecurity platform? "
    "Compare ecosystem, performance, state management at scale, and hiring."
)


async def main() -> int:
    # Windows consoles default to cp1252, which chokes on model output
    # (e.g. U+2011). Force UTF-8 like src/core/logging_config.py does.
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except (AttributeError, OSError):
        pass
    orch = Orchestrator()
    live = orch.router.get_available_providers()
    print(f"Live providers ({len(live)}): {', '.join(live)}")
    if len(live) < 3:
        print("ABORT: need at least 3 live providers for an execution.")
        return 2

    # Count real provider calls (names only — never keys).
    calls = {"count": 0}

    for provider in orch.router._providers.values():
        original_generate = provider.generate

        async def counting_generate(
            *args: Any, _original: Any = original_generate, **kwargs: Any
        ) -> Any:
            calls["count"] += 1
            return await _original(*args, **kwargs)

        provider.generate = counting_generate  # type: ignore[method-assign]

    consensus_rounds: list = []

    async def on_progress(event: dict) -> None:
        if event["event_type"] == "agent_update":
            print("\nTeam:")
            for agent in event["data"].get("agents", []):
                print(
                    f"  {agent['agent_id']} {agent['agent_type']}"
                    f" -> {agent['provider_name']}/{agent['model']}"
                )
        elif event["event_type"] == "consensus_update":
            score = event["data"].get("consensus_score", 0.0)
            round_no = event["data"].get("round", "?")
            decision = event["data"].get("decision", "?")
            consensus_rounds.append((round_no, score, decision))
        elif event["event_type"] == "status_update" and event["data"].get(
            "problem_type"
        ):
            print(
                f"Plan: type={event['data']['problem_type']} "
                f"complexity={event['data']['complexity']}"
            )

    print(f"\nQuestion: {QUESTION}")
    started = time.monotonic()
    result = await orch.execute(
        execution_id="smoke-run",
        question=QUESTION,
        time_budget_minutes=3,
        on_progress=on_progress,
    )
    elapsed = time.monotonic() - started

    print("\nConsensus per round:")
    for round_no, score, decision in consensus_rounds:
        print(f"  round {round_no}: score={score:.2f} decision={decision}")

    print(f"\nTotal provider calls: {calls['count']}")
    print(f"Total tokens: {result.total_tokens}")
    print(f"Wall-clock: {elapsed:.1f}s (budget 180s)")
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
    return 0 if result.status == "completed" else 1


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
