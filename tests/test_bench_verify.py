"""D: benchmark verification and guards (offline, no live calls)."""

import argparse
import csv
import json
from pathlib import Path

import pytest

from bench import analyze as analyze_mod
from bench.bench_common import (
    load_questions,
    remaining_questions,
)
from bench.grade import grade_all
from bench.verify_questions import (
    apply_verdict,
    import_csv,
    require_method,
    status_counts,
)


def _write_questions(path: Path, rows: list[dict]) -> None:
    with open(path, "w", encoding="utf-8") as fh:
        fh.writelines(json.dumps(row) + "\n" for row in rows)


def _q(
    qid: str, status: str = "unverified", answer_type: str = "exact", ref: str = "42"
) -> dict:
    return {
        "id": qid,
        "category": "math_science",
        "question": f"Q {qid}?",
        "answer_type": answer_type,
        "reference_answer": ref,
        "rubric": None,
        "difficulty": "easy",
        "verification": {
            "status": status,
            "verified_by": "Tester" if status == "verified" else None,
            "verified_at": None,
            "method": "computed" if status == "verified" else None,
            "source": None,
        },
    }


def test_unverified_excluded_under_verified_only(tmp_path: Path) -> None:
    path = tmp_path / "questions.jsonl"
    _write_questions(path, [_q("a-01", "verified"), _q("a-02", "unverified")])
    questions = load_questions(path)
    pending = remaining_questions(questions, set(), None, None, True, None)
    assert [q.id for q in pending] == ["a-01"]
    pending_all = remaining_questions(questions, set(), None, None, False, None)
    assert sorted(q.id for q in pending_all) == ["a-01", "a-02"]


def test_tool_refuses_verified_without_method() -> None:
    with pytest.raises(ValueError):
        require_method(None, None)
    with pytest.raises(ValueError):
        require_method("cited source", "")
    method, _source = require_method("computed", "")
    assert method == "computed"
    with pytest.raises(ValueError):
        apply_verdict(_q("a-01"), "verified", None, "", "", "")
    row = apply_verdict(_q("a-01"), "verified", None, "computed", "", "Tester")
    assert row["verification"]["status"] == "verified"


def test_import_only_applies_rows_with_method_and_name(tmp_path: Path) -> None:
    rows = [_q("a-01"), _q("a-02")]
    csv_path = tmp_path / "review.csv"
    with open(csv_path, "w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(
            fh,
            fieldnames=["id", "status", "method", "source", "reference_answer"],
        )
        writer.writeheader()
        writer.writerow(
            {
                "id": "a-01",
                "status": "verified",
                "method": "computed",
                "source": "",
                "reference_answer": "42",
            }
        )
        writer.writerow(
            {
                "id": "a-02",
                "status": "verified",
                "method": "",
                "source": "",
                "reference_answer": "42",
            }
        )
    updated = import_csv(rows, csv_path, "Tester")
    by_id = {r["id"]: r for r in updated}
    assert by_id["a-01"]["verification"]["status"] == "verified"
    assert by_id["a-02"]["verification"]["status"] == "unverified"


def test_status_counts() -> None:
    rows = [_q("a-01", "verified"), _q("a-02", "unverified"), _q("a-03", "rejected")]
    assert status_counts(rows) == {"unverified": 1, "verified": 1, "rejected": 1}


def test_analyze_header_and_refusal(tmp_path: Path) -> None:
    demo_rows, demo_records = analyze_mod.make_demo_data(1)
    assert analyze_mod.data_status(demo_rows, demo_records, True).startswith(
        "DATA STATUS: DEMO"
    )
    assert analyze_mod.is_final_ready(demo_rows, demo_records, True) is False

    good_rows = [
        {
            "question_id": "a-01",
            "system": "assembly",
            "score": 1.0,
            "verification_status": "verified",
            "live": True,
        },
        {
            "question_id": "a-01",
            "system": "single",
            "score": 0.0,
            "verification_status": "verified",
            "live": True,
        },
    ]
    assert analyze_mod.data_status(good_rows, [], False).startswith(
        "DATA STATUS: LIVE, VERIFIED"
    )
    assert analyze_mod.is_final_ready(good_rows, [], False) is True

    bad_rows = [
        {
            "question_id": "a-01",
            "system": "assembly",
            "score": 1.0,
            "verification_status": "unverified",
            "live": True,
        },
    ]
    assert "UNVERIFIED" in analyze_mod.data_status(bad_rows, [], False)
    assert analyze_mod.is_final_ready(bad_rows, [], False) is False


def test_analyze_demo_writes_preview_not_final(tmp_path: Path) -> None:
    code = analyze_mod.main(
        ["--demo", "--output-dir", str(tmp_path), "--charts-dir", str(tmp_path / "c")]
    )
    assert code == 2
    assert not (tmp_path / "REPORT.md").exists()
    assert (tmp_path / "REPORT.preview.md").exists()
    header = (tmp_path / "REPORT.preview.md").read_text(encoding="utf-8")
    assert "DATA STATUS: DEMO" in header


def test_schedule_math_on_fixtures() -> None:
    from bench.plan_schedule import plan_schedule

    plan = plan_schedule(40, 5, {"groq": 700.0, "openrouter": 35.0})
    assert plan["days"] >= 1
    assert plan["binding_provider"] == "openrouter"
    assert plan["total_calls"] == plan["calls_per_question"] * 40
    assert len(plan["schedule"]) == plan["days"]


def test_run_single_models_flag() -> None:
    from bench.run_single import parse_args

    args = parse_args(["--models", "a,b,c"])
    assert args.models == "a,b,c"
    args2 = parse_args([])
    assert args2.models is None
    assert getattr(args2, "verified_only", True) is True
    assert hasattr(args2, "seed")


def test_grade_verified_only_excludes_unverified(tmp_path: Path) -> None:
    import asyncio

    qpath = tmp_path / "questions.jsonl"
    _write_questions(tmp_path / "x.jsonl", [])
    _write_questions(qpath, [_q("a-01", "verified"), _q("a-02", "unverified")])
    results_dir = tmp_path / "results"
    results_dir.mkdir()
    run_path = results_dir / "r1.jsonl"
    with open(run_path, "w", encoding="utf-8") as fh:
        fh.writelines(
            json.dumps(
                {
                    "run_id": "r1",
                    "mode": "single",
                    "question_id": qid,
                    "category": "math_science",
                    "answer_type": "exact",
                    "difficulty": "easy",
                    "method": {"name": "single"},
                    "answer": "42",
                    "calls": 1,
                    "tokens": 10,
                    "seconds": 1.0,
                    "consensus_score": 1.0,
                    "errors": [],
                    "live": True,
                    "verification_status": "unverified",
                }
            )
            + "\n"
            for qid in ("a-01", "a-02")
        )
    args = argparse.Namespace(
        questions=qpath,
        questions_file=None,
        results_dir=results_dir,
        run_ids=["r1"],
        output_run_id=None,
        judge_provider=None,
        judge_model=None,
        max_tokens=10,
        per_question_timeout=5.0,
        max_wait_seconds=5.0,
        max_retries=0,
        env_file=None,
        app_mode=None,
        seed=1,
        limit=None,
        verified_only=True,
    )
    rows, _ = asyncio.run(grade_all(args))
    assert {r["question_id"] for r in rows} == {"a-01"}
