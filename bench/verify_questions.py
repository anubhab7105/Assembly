"""Assembly bench — human verification tool (offline, no LLM calls).

Interactive terminal review of bench/questions.jsonl draft answers. Shows
question, category, draft reference answer and rubric; choices:

  [v]erified as-is  [e]dit answer  [r]eject  [s]kip

Requires a method (computed / ran tests / cited source / other) and, for
non-computed answers, a source note. Writes back atomically. No bulk
"verify all".

Usage:
    python bench/verify_questions.py [--questions bench/questions.jsonl]
    python bench/verify_questions.py --status
    python bench/verify_questions.py --export-csv out.csv
    python bench/verify_questions.py --import-csv reviewed.csv --reviewer "Name"
"""

from __future__ import annotations

import argparse
import csv
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

BENCH_DIR = Path(__file__).resolve().parent
if str(BENCH_DIR.parent) not in sys.path:
    sys.path.insert(0, str(BENCH_DIR.parent))

DEFAULT_QUESTIONS = BENCH_DIR / "questions.jsonl"

ALLOWED_STATUSES = ("unverified", "verified", "rejected")
ALLOWED_METHODS = ("computed", "ran tests", "cited source", "other")


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--questions", type=Path, default=DEFAULT_QUESTIONS)
    parser.add_argument("--status", action="store_true", help="Print counts and exit.")
    parser.add_argument("--export-csv", type=Path, default=None)
    parser.add_argument("--import-csv", type=Path, default=None)
    parser.add_argument("--reviewer", default=None, help="Name for --import-csv.")
    parser.add_argument("--limit", type=int, default=None)
    return parser.parse_args(argv)


def load_raw(path: Path) -> list[dict]:
    rows: list[dict] = []
    with open(path, encoding="utf-8") as fh:
        for lineno, line in enumerate(fh, start=1):
            if not line.strip():
                continue
            try:
                rows.append(json.loads(line))
            except json.JSONDecodeError as exc:
                raise ValueError(f"{path}:{lineno}: invalid JSON: {exc}") from exc
    return rows


def write_atomic(path: Path, rows: list[dict]) -> None:
    tmp = path.with_suffix(".tmp")
    with open(tmp, "w", encoding="utf-8") as fh:
        fh.writelines(json.dumps(row, ensure_ascii=False) + "\n" for row in rows)
    os.replace(tmp, path)


def status_counts(rows: list[dict]) -> dict[str, int]:
    counts = {"unverified": 0, "verified": 0, "rejected": 0}
    for row in rows:
        status = str(((row.get("verification") or {}).get("status")) or "unverified")
        counts[status] = counts.get(status, 0) + 1
    return counts


def print_status(rows: list[dict]) -> None:
    counts = status_counts(rows)
    total = len(rows)
    print(
        f"Questions: {total} (verified={counts.get('verified', 0)}, "
        f"unverified={counts.get('unverified', 0)}, "
        f"rejected={counts.get('rejected', 0)})"
    )


def require_method(method: str | None, source: str | None) -> tuple[str, str]:
    """Validate a verification method/source pair (pure, unit-tested)."""
    clean_method = (method or "").strip().lower()
    if clean_method not in ALLOWED_METHODS:
        raise ValueError(
            f"method is required: one of {', '.join(ALLOWED_METHODS)} (got {method!r})"
        )
    clean_source = (source or "").strip()
    if clean_method != "computed" and not clean_source:
        raise ValueError("a source note is required for non-computed answers")
    return clean_method, clean_source


def apply_verdict(
    row: dict, verdict: str, answer: str | None, method: str, source: str, reviewer: str
) -> dict:
    """Apply one human verdict to a question row (pure, unit-tested)."""
    if verdict not in ("verified", "rejected"):
        raise ValueError(f"unknown verdict {verdict!r}")
    if verdict == "verified" and not reviewer.strip():
        raise ValueError("reviewer name is required")
    clean_method, clean_source = require_method(method, source)
    updated = dict(row)
    if verdict == "verified" and answer is not None:
        updated["reference_answer"] = answer
    verification = dict(updated.get("verification") or {})
    verification.update(
        {
            "status": verdict,
            "verified_by": reviewer.strip(),
            "verified_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "method": clean_method,
            "source": clean_source,
        }
    )
    updated["verification"] = verification
    return updated


def export_csv(rows: list[dict], out: Path) -> None:
    out.parent.mkdir(parents=True, exist_ok=True)
    with open(out, "w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(
            fh,
            fieldnames=[
                "id",
                "category",
                "question",
                "reference_answer",
                "rubric",
                "status",
                "method",
                "source",
                "verified_by",
            ],
        )
        writer.writeheader()
        for row in rows:
            verification = row.get("verification") or {}
            writer.writerow(
                {
                    "id": row.get("id", ""),
                    "category": row.get("category", ""),
                    "question": row.get("question", ""),
                    "reference_answer": row.get("reference_answer", ""),
                    "rubric": json.dumps(row.get("rubric"), ensure_ascii=False),
                    "status": verification.get("status", "unverified"),
                    "method": verification.get("method") or "",
                    "source": verification.get("source") or "",
                    "verified_by": verification.get("verified_by") or "",
                }
            )
    print(f"Exported {len(rows)} rows to {out}")


def import_csv(rows: list[dict], csv_path: Path, reviewer: str | None) -> list[dict]:
    """Apply spreadsheet review rows (only rows with method + reviewer name)."""
    if not reviewer or not reviewer.strip():
        raise SystemExit('ABORT: --import-csv requires --reviewer "Your Name".')
    by_id = {str(r.get("id")): r for r in rows}
    applied = 0
    skipped = 0
    with open(csv_path, encoding="utf-8", newline="") as fh:
        reader = csv.DictReader(fh)
        for line in reader:
            qid = str(line.get("id", "")).strip()
            row = by_id.get(qid)
            if row is None:
                skipped += 1
                continue
            status = str(line.get("status", "")).strip().lower()
            method = str(line.get("method", "")).strip()
            source = str(line.get("source", "")).strip()
            answer = line.get("reference_answer", "")
            if status not in ("verified", "rejected"):
                skipped += 1
                continue
            if not method or not reviewer.strip():
                skipped += 1
                continue
            try:
                updated = apply_verdict(row, status, answer, method, source, reviewer)
            except ValueError as exc:
                print(f"Skipping {qid}: {exc}")
                skipped += 1
                continue
            by_id[qid] = updated
            applied += 1
    print(f"Import: {applied} applied, {skipped} skipped (need method + reviewer).")
    order = [str(r.get("id")) for r in rows]
    return [by_id[qid] for qid in order]


def interactive(rows: list[dict], limit: int | None) -> list[dict]:
    reviewer = input("Reviewer name (required): ").strip()
    if not reviewer:
        raise SystemExit("ABORT: reviewer name is required.")
    pending = [
        r
        for r in rows
        if str((r.get("verification") or {}).get("status")) == "unverified"
    ]
    if limit is not None:
        pending = pending[:limit]
    ids = {str(r.get("id")) for r in pending}
    print(f"Reviewing {len(pending)} unverified question(s). No bulk verify-all.")
    for row in rows:
        if str(row.get("id")) not in ids:
            continue
        print("\n" + "=" * 72)
        print(f"[{row.get('id')}] {row.get('category')} / {row.get('difficulty')}")
        print(f"Q: {row.get('question')}")
        print(f"Draft reference: {row.get('reference_answer')}")
        if row.get("rubric"):
            print("Rubric:")
            for i, criterion in enumerate(row["rubric"], 1):
                print(f"  {i}. {criterion}")
        choice = (
            input("[v]erified as-is, [e]dit answer, [r]eject, [s]kip: ").strip().lower()
        )
        if choice == "s" or not choice:
            continue
        if choice not in ("v", "e", "r"):
            print("Skipped (unknown choice).")
            continue
        method = input(f"Method ({'/'.join(ALLOWED_METHODS)}): ").strip()
        source = ""
        if method.lower() != "computed":
            source = input("Source note (required for non-computed): ").strip()
        try:
            if choice == "r":
                updated = apply_verdict(row, "rejected", None, method, source, reviewer)
            elif choice == "e":
                print(f"Current: {row.get('reference_answer')}")
                new_answer = input("New reference answer: ")
                if not new_answer.strip():
                    print("Skipped (empty answer).")
                    continue
                updated = apply_verdict(
                    row, "verified", new_answer, method, source, reviewer
                )
            else:
                updated = apply_verdict(row, "verified", None, method, source, reviewer)
        except ValueError as exc:
            print(f"Not recorded: {exc}")
            continue
        row.clear()
        row.update(updated)
        print(f"Recorded {updated['verification']['status']} for {updated.get('id')}.")
    return rows


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    path = Path(args.questions)
    if not path.exists():
        raise SystemExit(f"ABORT: questions file not found: {path}")
    rows = load_raw(path)
    if args.status:
        print_status(rows)
        return 0
    if args.export_csv is not None:
        export_csv(rows, Path(args.export_csv))
        return 0
    if args.import_csv is not None:
        updated = import_csv(rows, Path(args.import_csv), args.reviewer)
        write_atomic(path, updated)
        print_status(updated)
        return 0
    updated = interactive(rows, args.limit)
    write_atomic(path, updated)
    print_status(updated)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
