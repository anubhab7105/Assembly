"""Assembly bench grader.

Grades one or more bench/results/<run_id>.jsonl files:

- exact/numeric questions are auto-graded with normalization;
- rubric questions are anonymized per question (A/B/C labels, shuffled)
  and scored by one LLM judge from a family outside the answerer family set
  when the live catalog can provide one;
- outputs bench/results/graded_<run_id>.csv plus a 20%+ rubric spot-check CSV.

Keys come from the local key store via ModelRouter. Keys are never printed.
"""

from __future__ import annotations

import argparse
import asyncio
import csv
import json
import math
import random
import re
import sys
import time
from collections import defaultdict
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field

BENCH_DIR = Path(__file__).resolve().parent
if str(BENCH_DIR.parent) not in sys.path:
    sys.path.insert(0, str(BENCH_DIR.parent))

from bench.bench_common import (
    DEFAULT_QUESTIONS,
    DEFAULT_RESULTS_DIR,
    AbortRunError,
    QuotaPolicy,
    apply_app_mode,
    ask_once,
    force_utf8_stdout,
    load_env_file,
    load_questions,
    load_secrets_best_effort,
)
from src.agents.base_agent import BaseAgent
from src.providers.base import ChatMessage
from src.providers.router import ModelRouter, RoutingDecision

MAX_RUBRIC_POINTS = 4.0
SPOT_CHECK_FRACTION = 0.20


class LoadedResult(BaseModel):
    """Subset of BenchResult plus flexible method metadata."""

    run_id: str
    mode: str
    question_id: str
    category: str
    answer_type: str
    difficulty: str = "medium"
    method: dict[str, Any] = Field(default_factory=dict)
    answer: str = ""
    calls: int = 0
    tokens: int = 0
    seconds: float = 0.0
    consensus_score: float | None = None
    errors: list[dict[str, str]] = Field(default_factory=list)
    live: bool = True
    verification_status: str = "unverified"

    @property
    def system(self) -> str:
        """Stable system name for summaries."""
        return str(self.method.get("name") or self.mode or self.run_id)

    @property
    def families(self) -> set[str]:
        """Families used by the answerer, best-effort from method metadata."""
        families: set[str] = set()
        family = self.method.get("family")
        if isinstance(family, str) and family:
            families.add(family)
        method_families = self.method.get("families")
        if isinstance(method_families, list):
            families.update(str(item) for item in method_families if item)
        votes = self.method.get("votes")
        if isinstance(votes, list):
            for vote in votes:
                if isinstance(vote, dict) and vote.get("family"):
                    families.add(str(vote["family"]))
        return families


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    """Parse CLI flags."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "run_ids",
        nargs="+",
        help="Run ids or .jsonl paths to grade/compare.",
    )
    parser.add_argument("--questions", type=Path, default=DEFAULT_QUESTIONS)
    parser.add_argument("--questions-file", type=Path, default=None)
    parser.add_argument("--results-dir", type=Path, default=DEFAULT_RESULTS_DIR)
    parser.add_argument(
        "--output-run-id",
        default=None,
        help="Suffix for graded_<id>.csv (default: first run id stem).",
    )
    parser.add_argument("--judge-provider", default=None)
    parser.add_argument("--judge-model", default=None)
    parser.add_argument("--max-tokens", type=int, default=1200)
    parser.add_argument("--per-question-timeout", type=float, default=120.0)
    parser.add_argument("--max-wait-seconds", type=float, default=120.0)
    parser.add_argument("--max-retries", type=int, default=3)
    parser.add_argument("--env-file", type=Path, default=None)
    parser.add_argument("--app-mode", default=None, choices=["dev", "web", "desktop"])
    parser.add_argument("--seed", type=int, default=20261008)
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument(
        "--verified-only",
        dest="verified_only",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="Only grade verified questions (default ON).",
    )
    return parser.parse_args(argv)


def _run_path(results_dir: Path, run_id_or_path: str) -> Path:
    """Resolve a run id or direct JSONL path."""
    path = Path(run_id_or_path)
    if path.suffix == ".jsonl" or path.exists():
        return path
    return results_dir / f"{run_id_or_path}.jsonl"


def load_results(results_dir: Path, run_ids: list[str]) -> list[LoadedResult]:
    """Load result JSONL files, tolerating partial last lines."""
    rows: list[LoadedResult] = []
    for run_id in run_ids:
        path = _run_path(results_dir, run_id)
        if not path.exists():
            raise FileNotFoundError(f"Result file not found: {path}")
        with open(path, encoding="utf-8") as fh:
            for line in fh:
                if not line.strip():
                    continue
                try:
                    rows.append(LoadedResult(**json.loads(line)))
                except (json.JSONDecodeError, TypeError, ValueError) as exc:
                    print(f"Skipping bad result line in {path}: {exc}")
    if not rows:
        raise ValueError("No result rows found")
    return rows


def strip_draft_marker(reference: str) -> str:
    """Remove the benchmark draft marker before comparing answers."""
    text = reference.strip()
    text = re.sub(
        r"^NEEDS\s+HUMAN\s+VERIFICATION\s+[-\u2014]*\s*draft:\s*",
        "",
        text,
        flags=re.IGNORECASE,
    )
    return text.strip()


def canonical_exact(text: str) -> str:
    """Normalize short exact answers."""
    text = strip_draft_marker(text)
    text = text.casefold()
    text = text.replace("2nd", "2").replace("1st", "1").replace("3rd", "3")
    text = re.sub(r"\b(second|two)\b", "2", text)
    text = re.sub(r"\b(first|one)\b", "1", text)
    text = re.sub(r"\b(third|three)\b", "3", text)
    text = re.sub(r"[^a-z0-9/=.]+", " ", text)
    return " ".join(text.split())


def exact_reference_candidates(reference: str) -> list[str]:
    """Possible exact-answer forms from a draft reference."""
    clean = strip_draft_marker(reference)
    candidates = [clean]
    before_paren = clean.split("(", 1)[0].strip()
    if before_paren:
        candidates.append(before_paren)
    candidates.extend(re.findall(r"\(([^)]*)\)", clean))
    expanded: list[str] = []
    for candidate in candidates:
        expanded.append(candidate)
        expanded.extend(re.split(r"\s+or\s+|;", candidate, flags=re.IGNORECASE))
    normalized = [canonical_exact(candidate) for candidate in expanded]
    return [candidate for candidate in dict.fromkeys(normalized) if candidate]


def exact_score(answer: str, reference: str) -> tuple[float, str]:
    """Score exact answers after normalization."""
    got = canonical_exact(answer)
    expected_candidates = exact_reference_candidates(reference)
    if not got or not expected_candidates:
        return 0.0, "missing answer or reference"
    for expected in expected_candidates:
        if got == expected or expected in got:
            return 1.0, "normalized exact match"
        got_tokens = set(got.split())
        expected_tokens = set(expected.split())
        if got_tokens and got_tokens == expected_tokens:
            return 1.0, "normalized exact match"
    expected = expected_candidates[0]
    if len(got.split()) == 1 and got in expected_candidates:
        return 1.0, "normalized exact match"
    return 0.0, f"expected normalized '{expected}', got '{got[:120]}'"


def _numbers(text: str) -> list[float]:
    """Extract numeric literals from text."""
    return [float(x) for x in re.findall(r"[-+]?\d+(?:\.\d+)?", text)]


def numeric_interval(question: str, reference: str) -> tuple[float, float] | None:
    """Find an explicit accepted numeric range, if the prompt/reference has one."""
    joined = f"{question}\n{reference}"
    match = re.search(
        r"(?:accept(?:s|ed)?\s*)?(?:any value in\s*)?\[?\s*"
        r"([-+]?\d+(?:\.\d+)?)\s*[,–-]\s*([-+]?\d+(?:\.\d+)?)\s*\]?",
        joined,
        flags=re.IGNORECASE,
    )
    if not match:
        return None
    lo, hi = float(match.group(1)), float(match.group(2))
    return (min(lo, hi), max(lo, hi))


def numeric_score(answer: str, reference: str, question: str) -> tuple[float, str]:
    """Score numeric answers with range/tolerance support."""
    got_numbers = _numbers(answer)
    if not got_numbers:
        return 0.0, "no numeric value found"
    got = got_numbers[0]
    interval = numeric_interval(question, reference)
    if interval is not None:
        lo, hi = interval
        return (
            (1.0, f"{got} inside accepted range [{lo}, {hi}]")
            if lo <= got <= hi
            else (0.0, f"{got} outside accepted range [{lo}, {hi}]")
        )
    ref_numbers = _numbers(strip_draft_marker(reference))
    if not ref_numbers:
        return 0.0, "no numeric reference found"
    expected = ref_numbers[0]
    tolerance = max(1e-6, abs(expected) * 1e-6)
    if math.isclose(got, expected, rel_tol=1e-6, abs_tol=tolerance):
        return 1.0, f"{got} matches {expected}"
    return 0.0, f"expected {expected}, got {got}"


def select_judge(
    router: ModelRouter,
    answerer_families: set[str],
    prefer_provider: str | None,
    prefer_model: str | None,
) -> tuple[RoutingDecision, str | None]:
    """Pick a judge outside answerer families when possible."""
    candidates: list[RoutingDecision] = []
    for role in ("critic", "solver", "synthesizer"):
        for provider_id, model_id, family in router._candidates(role):
            provider = router._providers[provider_id]
            if prefer_provider and provider_id != prefer_provider:
                continue
            if prefer_model and model_id != prefer_model:
                continue
            candidates.append(
                RoutingDecision(
                    provider=provider,
                    model=model_id,
                    provider_name=provider_id,
                    family=family,
                    role=role,
                    reason="benchmark rubric judge",
                )
            )
    if not candidates:
        return router.route("critic", prefer_provider=prefer_provider), (
            "requested judge unavailable; fell back to router"
        )
    for candidate in candidates:
        if candidate.family not in answerer_families:
            return candidate, None
    return candidates[0], (
        "no live judge family outside all answerer families; "
        "rubric score may be more biased"
    )


def build_rubric_judge_messages(
    question: str,
    rubric: list[str],
    labeled_answers: dict[str, str],
) -> list[ChatMessage]:
    """Strict hidden-label judge prompt."""
    answers = "\n\n".join(
        f"ANSWER {label}:\n{answer or '[blank answer]'}"
        for label, answer in labeled_answers.items()
    )
    rubric_lines = "\n".join(
        f"{index + 1}. {criterion}" for index, criterion in enumerate(rubric)
    )
    labels = ", ".join(labeled_answers)
    return [
        ChatMessage(
            role="system",
            content=(
                "You are a strict benchmark judge. The answer system names are "
                "hidden; judge only the labeled text. Grade each answer against "
                "the rubric independently. Return only valid JSON."
            ),
        ),
        ChatMessage(
            role="user",
            content=(
                f"Question:\n{question}\n\nRubric criteria, one point each:\n"
                f"{rubric_lines}\n\n{answers}\n\nReturn exactly this JSON shape:\n"
                '{"scores":{"A":{"score":0,"criteria":[false,false,false,false],'
                '"rationale":"brief"}}}\n'
                f"Include every label: {labels}. Scores may be 0 through "
                f"{len(rubric)} and criteria must be booleans."
            ),
        ),
    ]


def parse_judge_json(text: str) -> dict[str, Any]:
    """Parse a judge JSON object using the hardened extractor."""
    extracted = BaseAgent._extract_json(text)
    if extracted is None:
        raise ValueError("judge returned no JSON object")
    data = json.loads(extracted)
    if not isinstance(data, dict) or not isinstance(data.get("scores"), dict):
        raise TypeError("judge JSON missing scores object")
    return data


async def judge_rubric_question(
    rows: list[LoadedResult],
    question: Any,
    router: ModelRouter,
    args: argparse.Namespace,
    policy: QuotaPolicy,
    secrets: list[str],
) -> tuple[dict[str, dict[str, Any]], dict[str, Any]]:
    """Grade one rubric question with anonymized labels."""
    answerer_families: set[str] = set()
    for row in rows:
        answerer_families.update(row.families)
    judge, warning = select_judge(
        router, answerer_families, args.judge_provider, args.judge_model
    )
    shuffled = list(rows)
    rng = random.Random(f"{args.seed}:{question.id}")
    rng.shuffle(shuffled)
    label_for_key = {
        (row.run_id, row.system): chr(65 + index) for index, row in enumerate(shuffled)
    }
    labeled_answers = {
        label_for_key[(row.run_id, row.system)]: row.answer for row in shuffled
    }
    outcome = await ask_once(
        judge.provider,
        judge.model,
        build_rubric_judge_messages(
            question.question, question.rubric or [], labeled_answers
        ),
        policy=policy,
        timeout_seconds=args.per_question_timeout,
        max_tokens=args.max_tokens,
        secrets=secrets,
    )
    if not outcome.text:
        raise ValueError(f"judge failed: {outcome.errors}")
    parsed = parse_judge_json(outcome.text)
    scores = parsed["scores"]
    by_row: dict[str, dict[str, Any]] = {}
    for row in rows:
        label = label_for_key[(row.run_id, row.system)]
        raw = scores.get(label, {})
        criteria = raw.get("criteria", [])
        if not isinstance(criteria, list):
            criteria = []
        score = raw.get("score")
        if not isinstance(score, int | float):
            score = sum(1 for item in criteria if item is True)
        score = max(0.0, min(float(score), float(len(question.rubric or []))))
        by_row[f"{row.run_id}:{row.system}"] = {
            "label": label,
            "score": score,
            "max_score": float(len(question.rubric or [])),
            "criteria_json": json.dumps(criteria, ensure_ascii=False),
            "rationale": str(raw.get("rationale", ""))[:500],
        }
    meta = {
        "judge_provider": judge.provider_name,
        "judge_model": judge.model,
        "judge_family": judge.family,
        "judge_warning": warning or "",
        "judge_calls": outcome.calls,
        "judge_tokens": outcome.tokens,
    }
    return by_row, meta


def _blank_grade(row: LoadedResult, max_score: float, rationale: str) -> dict[str, Any]:
    """CSV row for ungraded/error cases."""
    return {
        "run_id": row.run_id,
        "system": row.system,
        "question_id": row.question_id,
        "category": row.category,
        "answer_type": row.answer_type,
        "difficulty": row.difficulty,
        "score": 0.0,
        "max_score": max_score,
        "correct": False,
        "judge_label": "",
        "judge_provider": "",
        "judge_model": "",
        "judge_family": "",
        "judge_warning": "",
        "rationale": rationale,
        "criteria_json": "",
        "manual_spot_check": False,
        "answer_excerpt": row.answer[:300].replace("\n", " "),
        "live": bool(getattr(row, "live", True)),
        "verification_status": str(getattr(row, "verification_status", "unverified")),
    }


async def grade_all(
    args: argparse.Namespace,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Grade all loaded rows and return CSV rows plus judge usage."""
    qpath = getattr(args, "questions_file", None) or args.questions
    questions = {q.id: q for q in load_questions(Path(qpath))}
    results = load_results(args.results_dir, args.run_ids)
    # --verified-only (default ON): drop unverified questions before grading.
    if getattr(args, "verified_only", True):
        results = [
            r
            for r in results
            if (questions.get(r.question_id) is not None)
            and (
                getattr(questions[r.question_id].verification, "status", "unverified")
                == "verified"
            )
        ]
    # --limit + --seed: deterministic subset for pilots.
    limit = getattr(args, "limit", None)
    seed = getattr(args, "seed", 20261008)
    if limit is not None:
        import random as _random

        order = sorted({r.question_id for r in results})
        rng = _random.Random(seed)
        rng.shuffle(order)
        keep = set(order[:limit])
        results = [r for r in results if r.question_id in keep]
    by_question: dict[str, list[LoadedResult]] = defaultdict(list)
    for row in results:
        by_question[row.question_id].append(row)

    rubric_needed = any(
        questions[row.question_id].answer_type == "rubric"
        for row in results
        if row.question_id in questions
    )
    router: ModelRouter | None = ModelRouter() if rubric_needed else None
    policy = QuotaPolicy(
        max_retries=args.max_retries, max_wait_seconds=args.max_wait_seconds
    )
    secrets = load_secrets_best_effort()
    graded: list[dict[str, Any]] = []
    judge_usage = {"calls": 0, "tokens": 0}

    for question_id, rows in by_question.items():
        question = questions.get(question_id)
        if question is None:
            for row in rows:
                graded.append(
                    _blank_grade(row, 1.0, "question id missing from questions file")
                )
            continue
        if question.answer_type == "numeric":
            for row in rows:
                score, rationale = numeric_score(
                    row.answer, question.reference_answer, question.question
                )
                out = _blank_grade(row, 1.0, rationale)
                out["score"] = score
                out["correct"] = score == 1.0
                graded.append(out)
        elif question.answer_type == "exact":
            for row in rows:
                score, rationale = exact_score(row.answer, question.reference_answer)
                out = _blank_grade(row, 1.0, rationale)
                out["score"] = score
                out["correct"] = score == 1.0
                graded.append(out)
        elif question.answer_type == "rubric":
            assert router is not None
            try:
                scores, meta = await judge_rubric_question(
                    rows, question, router, args, policy, secrets
                )
                judge_usage["calls"] += int(meta["judge_calls"])
                judge_usage["tokens"] += int(meta["judge_tokens"])
                for row in rows:
                    key = f"{row.run_id}:{row.system}"
                    grade = scores[key]
                    out = _blank_grade(row, grade["max_score"], grade["rationale"])
                    out.update(
                        {
                            "score": grade["score"],
                            "max_score": grade["max_score"],
                            "correct": grade["score"] == grade["max_score"],
                            "judge_label": grade["label"],
                            "judge_provider": meta["judge_provider"],
                            "judge_model": meta["judge_model"],
                            "judge_family": meta["judge_family"],
                            "judge_warning": meta["judge_warning"],
                            "criteria_json": grade["criteria_json"],
                        }
                    )
                    graded.append(out)
            except AbortRunError:
                raise
            except Exception as exc:  # noqa: BLE001 - grade rest of run
                for row in rows:
                    graded.append(
                        _blank_grade(
                            row,
                            MAX_RUBRIC_POINTS,
                            f"rubric judge failed: {type(exc).__name__}",
                        )
                    )
        else:
            for row in rows:
                graded.append(
                    _blank_grade(
                        row, 1.0, f"unknown answer_type {question.answer_type}"
                    )
                )

    mark_spot_checks(graded, args.seed)
    return graded, judge_usage


def mark_spot_checks(rows: list[dict[str, Any]], seed: int) -> None:
    """Mark at least 20% of rubric rows for manual spot check."""
    rubric_rows = [row for row in rows if row["answer_type"] == "rubric"]
    if not rubric_rows:
        return
    count = max(1, math.ceil(len(rubric_rows) * SPOT_CHECK_FRACTION))
    rng = random.Random(f"{seed}:spotcheck")
    for row in rng.sample(rubric_rows, count):
        row["manual_spot_check"] = True


def write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    """Write rows to CSV."""
    path.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = [
        "run_id",
        "system",
        "question_id",
        "category",
        "answer_type",
        "difficulty",
        "score",
        "max_score",
        "correct",
        "judge_label",
        "judge_provider",
        "judge_model",
        "judge_family",
        "judge_warning",
        "rationale",
        "criteria_json",
        "manual_spot_check",
        "answer_excerpt",
        "live",
        "verification_status",
    ]
    with open(path, "w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def summarize(rows: list[dict[str, Any]]) -> str:
    """Build win/tie/loss and mean-score summary."""
    systems = sorted({row["system"] for row in rows})
    by_question: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        by_question[row["question_id"]].append(row)

    wtl = {system: {"win": 0, "tie": 0, "loss": 0} for system in systems}
    for qrows in by_question.values():
        if not qrows:
            continue
        best = max(float(row["score"]) for row in qrows)
        winners = [row for row in qrows if float(row["score"]) == best]
        for row in qrows:
            bucket = (
                "tie"
                if len(winners) > 1 and float(row["score"]) == best
                else ("win" if float(row["score"]) == best else "loss")
            )
            wtl[row["system"]][bucket] += 1

    means: dict[tuple[str, str], list[float]] = defaultdict(list)
    system_means: dict[str, list[float]] = defaultdict(list)
    for row in rows:
        ratio = float(row["score"]) / float(row["max_score"] or 1.0)
        system_means[row["system"]].append(ratio)
        means[(row["system"], row["category"])].append(ratio)

    lines = ["Summary:"]
    for system in systems:
        values = system_means[system]
        mean = sum(values) / len(values) if values else 0.0
        counts = wtl[system]
        lines.append(
            f"- {system}: W/T/L={counts['win']}/{counts['tie']}/{counts['loss']}, "
            f"mean={mean:.3f}"
        )
    lines.append("Mean by system/category:")
    for (system, category), values in sorted(means.items()):
        lines.append(f"- {system}/{category}: {sum(values) / len(values):.3f}")
    return "\n".join(lines)


def output_id(args: argparse.Namespace) -> str:
    """Choose graded_<id>.csv suffix."""
    if args.output_run_id:
        return args.output_run_id
    first = Path(args.run_ids[0]).stem
    return first


def main(argv: list[str] | None = None) -> int:
    """CLI entry."""
    force_utf8_stdout()
    args = parse_args(argv)
    load_env_file(args.env_file)
    apply_app_mode(args.app_mode)
    started = time.monotonic()
    try:
        rows, judge_usage = asyncio.run(grade_all(args))
    except KeyboardInterrupt:
        print("\nInterrupted during grading.")
        return 130
    except AbortRunError as exc:
        print(f"ABORT: {exc}")
        return 1
    out_id = output_id(args)
    graded_path = args.results_dir / f"graded_{out_id}.csv"
    spot_path = args.results_dir / f"graded_{out_id}_spotcheck.csv"
    write_csv(graded_path, rows)
    write_csv(spot_path, [row for row in rows if row["manual_spot_check"]])
    print(f"Wrote {graded_path}")
    print(f"Wrote {spot_path}")
    print(
        f"Judge usage: {judge_usage['calls']} calls, "
        f"{judge_usage['tokens']} tokens, {time.monotonic() - started:.1f}s"
    )
    print(summarize(rows))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
