"""Offline tests for bench/grade.py."""

from __future__ import annotations

import argparse
import asyncio
import csv
import json
from pathlib import Path

from bench import grade


def test_numeric_score_accepts_explicit_range() -> None:
    score, rationale = grade.numeric_score(
        "The pH is about 6.98.",
        "NEEDS HUMAN VERIFICATION - draft: 6.98 (accept 6.9-7.0)",
        "Accept any value in [6.9, 7.0].",
    )

    assert score == 1.0
    assert "inside accepted range" in rationale


def test_exact_score_accepts_parenthesized_equivalent() -> None:
    score, _ = grade.exact_score(
        "2",
        "NEEDS HUMAN VERIFICATION - draft: 2nd (2)",
    )

    assert score == 1.0


def test_rubric_judge_prompt_hides_system_names() -> None:
    messages = grade.build_rubric_judge_messages(
        "Question?",
        ["Criterion one", "Criterion two"],
        {"A": "alpha answer", "B": "beta answer"},
    )
    joined = "\n".join(message.content for message in messages)

    assert "ANSWER A" in joined
    assert "ANSWER B" in joined
    assert "single" not in joined.casefold()
    assert "assembly" not in joined.casefold()


def test_auto_grade_writes_spotcheck_free_csv(tmp_path: Path) -> None:
    questions = tmp_path / "questions.jsonl"
    results_dir = tmp_path / "results"
    results_dir.mkdir()
    questions.write_text(
        "\n".join(
            [
                json.dumps(
                    {
                        "id": "n1",
                        "category": "math_science",
                        "question": "What is 2+2?",
                        "answer_type": "numeric",
                        "reference_answer": "NEEDS HUMAN VERIFICATION - draft: 4",
                        "rubric": None,
                        "difficulty": "easy",
                    }
                ),
                json.dumps(
                    {
                        "id": "e1",
                        "category": "logic_reasoning",
                        "question": "Valid or invalid?",
                        "answer_type": "exact",
                        "reference_answer": "NEEDS HUMAN VERIFICATION - draft: invalid",
                        "rubric": None,
                        "difficulty": "easy",
                    }
                ),
            ]
        ),
        encoding="utf-8",
    )
    (results_dir / "demo.jsonl").write_text(
        "\n".join(
            [
                json.dumps(
                    {
                        "run_id": "demo",
                        "mode": "single",
                        "question_id": "n1",
                        "category": "math_science",
                        "answer_type": "numeric",
                        "answer": "4",
                    }
                ),
                json.dumps(
                    {
                        "run_id": "demo",
                        "mode": "single",
                        "question_id": "e1",
                        "category": "logic_reasoning",
                        "answer_type": "exact",
                        "answer": "Invalid.",
                    }
                ),
            ]
        ),
        encoding="utf-8",
    )
    args = argparse.Namespace(
        questions=questions,
        results_dir=results_dir,
        run_ids=["demo"],
        output_run_id="demo",
        judge_provider=None,
        judge_model=None,
        max_tokens=100,
        per_question_timeout=1.0,
        max_wait_seconds=1.0,
        max_retries=0,
        env_file=None,
        app_mode=None,
        seed=1,
    )

    rows, judge_usage = asyncio.run(grade.grade_all(args))
    out = results_dir / "graded_demo.csv"
    grade.write_csv(out, rows)

    assert judge_usage == {"calls": 0, "tokens": 0}
    assert [row["score"] for row in rows] == [1.0, 1.0]
    with open(out, encoding="utf-8", newline="") as fh:
        written = list(csv.DictReader(fh))
    assert len(written) == 2
