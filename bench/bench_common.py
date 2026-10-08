"""Assembly benchmark — shared helpers for bench/run_*.py.

One home for question loading, result records, resume support, quota-aware
single-call handling, and key-safe output. The three runners stay thin;
everything here is offline-testable with MockProvider.

Key rules (never relaxed):
- Keys come from the local key store (APP_MODE-selected) and are never
  printed, logged, or written to result files. Error strings pass through
  redact() with the live key values before they touch disk.
- Only provider/model/family NAMES appear in logs and result records.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_QUESTIONS = PROJECT_ROOT / "bench" / "questions.jsonl"
DEFAULT_RESULTS_DIR = PROJECT_ROOT / "bench" / "results"

if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.core.logging_config import logger
from src.providers.base import AIProvider, ChatMessage
from src.providers.errors import (
    AuthError,
    BadResponse,
    ProviderDown,
    ProviderError,
    RateLimited,
    classify_exception,
)
from src.providers.quota import QuotaExhausted


class BenchQuestion(BaseModel):
    """One benchmark question (subset of the questions.jsonl schema)."""

    id: str
    category: str
    question: str
    answer_type: str = "exact"
    reference_answer: str = ""
    rubric: list[str] | None = None
    difficulty: str = "medium"


class BenchResult(BaseModel):
    """One graded-input record written to bench/results/<run_id>.jsonl."""

    run_id: str
    mode: str
    question_id: str
    category: str
    answer_type: str
    difficulty: str
    method: dict[str, Any] = Field(default_factory=dict)
    answer: str = ""
    calls: int = 0
    tokens: int = 0
    seconds: float = 0.0
    consensus_score: float | None = None
    errors: list[dict[str, str]] = Field(default_factory=list)


@dataclass
class QuotaPolicy:
    """Bounded quota backoff for bench calls.

    Rate-limit/cooldown hits sleep (honoring the server's retry_after,
    capped by max_wait_seconds) and retry up to max_retries times. Anything
    else — spent daily quota, auth failures, bad responses, timeouts — is
    recorded as a per-question error so the run continues.
    """

    max_retries: int = 3
    max_wait_seconds: float = 120.0
    default_cooldown_seconds: float = 60.0


@dataclass
class AskOutcome:
    """Result of one quota-aware model call (possibly retried)."""

    text: str = ""
    tokens: int = 0
    calls: int = 0
    errors: list[dict[str, str]] = field(default_factory=list)


class AbortRunError(Exception):
    """Authentication is broken — retrying cannot help, stop the run."""


async def _sleep(seconds: float) -> None:
    """Sleep seam (tests monkeypatch bench.bench_common._sleep)."""
    await asyncio.sleep(seconds)


def utc_stamp() -> str:
    """Compact UTC timestamp for default run ids."""
    return datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")


def default_run_id(mode: str) -> str:
    """Default run id: <mode>-<utc stamp> (pass --run-id to resume)."""
    return f"{mode}-{utc_stamp()}"


def redact(text: str, secrets: list[str]) -> str:
    """Replace known secret values with *** (best-effort, fail-open)."""
    clean = text
    for secret in secrets:
        if secret and len(secret) >= 4 and secret in clean:
            clean = clean.replace(secret, "***")
    return clean


def load_secrets_best_effort() -> list[str]:
    """Live key values for redact(). Empty on any trouble — never logged."""
    try:
        from src.core.keystore import get_keystore, reveal

        return [reveal(v) for v in get_keystore().get_keys().values() if reveal(v)]
    except Exception:  # noqa: BLE001 — redaction is defense-in-depth, not critical
        return []


def load_questions(path: Path) -> list[BenchQuestion]:
    """Load and validate questions.jsonl (blank lines skipped)."""
    questions: list[BenchQuestion] = []
    with open(path, encoding="utf-8") as fh:
        for lineno, line in enumerate(fh, start=1):
            if not line.strip():
                continue
            try:
                data = json.loads(line)
            except json.JSONDecodeError as exc:
                raise ValueError(f"{path}:{lineno}: invalid JSON: {exc}") from exc
            try:
                questions.append(BenchQuestion(**data))
            except Exception as exc:
                raise ValueError(f"{path}:{lineno}: bad question: {exc}") from exc
    if not questions:
        raise ValueError(f"{path}: no questions found")
    ids = [q.id for q in questions]
    if len(set(ids)) != len(ids):
        raise ValueError(f"{path}: duplicate question ids")
    return questions


def normalize_text(text: str) -> str:
    """Normalization for vote comparison: strip, casefold, collapse space."""
    return " ".join(text.strip().casefold().split())


def majority_winner(answers: list[str]) -> tuple[str | None, int]:
    """String-level majority over normalized answers.

    Returns (winning raw answer, vote count), or (None, top count) when no
    answer reaches 2+ votes (a tie under 3 voters).
    """
    counts: dict[str, int] = {}
    raw: dict[str, str] = {}
    for answer in answers:
        key = normalize_text(answer)
        counts[key] = counts.get(key, 0) + 1
        raw.setdefault(key, answer)
    if not counts:
        return None, 0
    best = max(counts, key=lambda k: counts[k])
    if counts[best] >= 2:
        return raw[best], counts[best]
    return None, counts[best]


def match_candidate(reply: str, candidates: list[str]) -> str | None:
    """Return the candidate whose normalized text equals the reply, if any."""
    want = normalize_text(reply)
    for candidate in candidates:
        if normalize_text(candidate) == want:
            return candidate
    return None


def build_single_messages(question: str) -> list[ChatMessage]:
    """Direct-answer prompt for single/vote calls (no agent JSON contract)."""
    return [
        ChatMessage(
            role="system",
            content=(
                "Answer the question directly and concisely. "
                "For coding questions, output only the requested values."
            ),
        ),
        ChatMessage(role="user", content=question),
    ]


def build_judge_messages(question: str, candidates: list[str]) -> list[ChatMessage]:
    """Judge prompt: pick the best of the labeled candidate answers."""
    labeled = "\n\n".join(
        f"--- CANDIDATE {chr(65 + i)} ---\n{text}" for i, text in enumerate(candidates)
    )
    return [
        ChatMessage(
            role="system",
            content=(
                "You are an impartial judge. Reply with the full text of the "
                "better answer and nothing else."
            ),
        ),
        ChatMessage(
            role="user",
            content=f"Question:\n{question}\n\n{labeled}",
        ),
    ]


def _cooldown_wait(retry_after: float | None, policy: QuotaPolicy) -> float | None:
    """Seconds to sleep for a cooldown, or None when it exceeds the cap."""
    wait = (
        retry_after
        if retry_after is not None and retry_after > 0
        else policy.default_cooldown_seconds
    )
    if wait > policy.max_wait_seconds:
        return None
    return wait


async def ask_once(
    provider: AIProvider,
    model: str,
    messages: list[ChatMessage],
    *,
    policy: QuotaPolicy,
    timeout_seconds: float,
    max_tokens: int = 1024,
    secrets: list[str] | None = None,
) -> AskOutcome:
    """Call a provider once, sleeping through rate-limit cooldowns.

    Returns an AskOutcome (possibly with errors and empty text) for anything
    recoverable-or-recordable. Raises AbortRunError on auth failure.
    """
    name = provider.provider_name
    hidden: list[str] = secrets or []
    outcome = AskOutcome()
    attempts = 0
    while True:
        attempts += 1
        outcome.calls += 1
        try:
            response = await asyncio.wait_for(
                provider.generate(
                    messages, model=model, temperature=0.2, max_tokens=max_tokens
                ),
                timeout=timeout_seconds,
            )
        except (TimeoutError, asyncio.TimeoutError):
            outcome.errors.append(
                {
                    "phase": "generate",
                    "type": "TimeoutError",
                    "message": redact(f"{name} timed out", hidden),
                }
            )
            return outcome
        except Exception as exc:
            if isinstance(exc, AuthError):
                raise AbortRunError(
                    f"{name}: authentication failed — check the key, aborting run"
                ) from exc
            if isinstance(exc, QuotaExhausted):
                reason = exc.reason.casefold()
                if "daily" in reason or "spent" in reason:
                    outcome.errors.append(
                        {
                            "phase": "quota",
                            "type": "QuotaExhausted",
                            "message": redact(f"{name}: daily quota spent", hidden),
                        }
                    )
                    return outcome
                wait = _cooldown_wait(exc.retry_after, policy)
                if wait is not None and attempts <= policy.max_retries:
                    logger.warning(
                        f"Bench   │ {name} cooling down; "
                        f"sleeping {wait:.0f}s (attempt {attempts})"
                    )
                    await _sleep(wait)
                    continue
                outcome.errors.append(
                    {
                        "phase": "quota",
                        "type": "QuotaExhausted",
                        "message": redact(f"{name}: quota exhausted", hidden),
                    }
                )
                return outcome
            structured: Exception = (
                exc if isinstance(exc, ProviderError) else classify_exception(name, exc)
            )
            if isinstance(structured, RateLimited):
                wait = _cooldown_wait(structured.retry_after, policy)
                if wait is not None and attempts <= policy.max_retries:
                    logger.warning(
                        f"Bench   │ {name} rate-limited; "
                        f"sleeping {wait:.0f}s (attempt {attempts})"
                    )
                    await _sleep(wait)
                    continue
                outcome.errors.append(
                    {
                        "phase": "generate",
                        "type": "RateLimited",
                        "message": redact(f"{name} rate limit exceeded", hidden),
                    }
                )
                return outcome
            if isinstance(structured, (ProviderDown, BadResponse)):
                outcome.errors.append(
                    {
                        "phase": "generate",
                        "type": type(structured).__name__,
                        "message": redact(f"{name}: {structured.message}", hidden),
                    }
                )
                return outcome
            outcome.errors.append(
                {
                    "phase": "generate",
                    "type": type(exc).__name__,
                    "message": redact(f"{name}: unexpected error", hidden),
                }
            )
            return outcome
        outcome.text = response.content
        outcome.tokens += response.total_tokens
        return outcome


class ResultStore:
    """Append-only JSONL result file with resume support."""

    def __init__(self, path: Path) -> None:
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def done_ids(self) -> set[str]:
        """Question ids already recorded (tolerates partial last lines)."""
        done: set[str] = set()
        if not self.path.exists():
            return done
        with open(self.path, encoding="utf-8") as fh:
            for line in fh:
                if not line.strip():
                    continue
                try:
                    done.add(json.loads(line)["question_id"])
                except (json.JSONDecodeError, KeyError, TypeError):
                    continue
        return done

    def append(self, result: BenchResult) -> None:
        """Append one record (names only — BenchResult never holds keys)."""
        with open(self.path, encoding="utf-8", mode="a") as fh:
            fh.write(result.model_dump_json() + "\n")


def add_common_args(parser: argparse.ArgumentParser) -> argparse.ArgumentParser:
    """CLI flags shared by all three runners."""
    parser.add_argument("--questions", type=Path, default=DEFAULT_QUESTIONS)
    parser.add_argument("--results-dir", type=Path, default=DEFAULT_RESULTS_DIR)
    parser.add_argument(
        "--run-id",
        default=None,
        help="Resume/extend this run id (default: fresh <mode>-<utc stamp>)",
    )
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument(
        "--category",
        default=None,
        choices=["math_science", "logic_reasoning", "coding", "research"],
    )
    parser.add_argument("--max-tokens", type=int, default=1024)
    parser.add_argument("--per-question-timeout", type=float, default=120.0)
    parser.add_argument("--max-wait-seconds", type=float, default=120.0)
    parser.add_argument("--max-retries", type=int, default=3)
    parser.add_argument("--sleep-between-seconds", type=float, default=1.0)
    parser.add_argument("--env-file", type=Path, default=None)
    parser.add_argument("--app-mode", default=None, choices=["dev", "web", "desktop"])
    return parser


def force_utf8_stdout() -> None:
    """Windows cp1252 chokes on model output — force UTF-8 like scripts/."""
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except (AttributeError, OSError):
        pass


def load_env_file(env_file: Path | None) -> None:
    """Load keys file: explicit --env-file, else .env.dev when present."""
    from dotenv import load_dotenv

    if env_file is not None:
        load_dotenv(env_file, override=False)
        return
    fallback = PROJECT_ROOT / ".env.dev"
    if fallback.exists():
        load_dotenv(fallback, override=False)


def apply_app_mode(app_mode: str | None) -> None:
    """Override settings.app_mode for this process when requested."""
    if app_mode is None:
        return
    from src.core.config import settings

    settings.app_mode = app_mode  # type: ignore[assignment]


def remaining_questions(
    questions: list[BenchQuestion],
    done: set[str],
    category: str | None,
    limit: int | None,
) -> list[BenchQuestion]:
    """Skip answered ids, filter by category, then cap at limit."""
    pending = [q for q in questions if q.id not in done]
    if category is not None:
        pending = [q for q in pending if q.category == category]
    if limit is not None:
        pending = pending[:limit]
    return pending


def print_summary(mode: str, results: list[BenchResult], elapsed: float) -> None:
    """Names-and-counts summary (never keys, never full answers)."""
    answered = sum(1 for r in results if r.answer)
    failed = len(results) - answered
    print(
        f"\n[{mode}] done: {answered} answered, {failed} failed, "
        f"{sum(r.calls for r in results)} calls, "
        f"{sum(r.tokens for r in results)} tokens, {elapsed:.1f}s"
    )
