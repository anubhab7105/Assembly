"""Assembly quota report: today's usage from persisted counters.

Reads the local quota_usage table (per-provider/model/day call + token
counters written by the quota limiter) and prints calls and tokens used
today per (provider, model), plus the time until each daily window
resets at UTC midnight.

Reads database rows only: no API keys (only salted fingerprints exist in
the table and they are never printed — rows aggregate per model), no
network. SQLite files only; anything else exits with an explanation.

Usage:
    python scripts/quota_report.py [--db PATH]
"""

from __future__ import annotations

import argparse
import sqlite3
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    """Parse quota_report CLI flags."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--db",
        type=Path,
        default=None,
        help="SQLite file to read (default: the app's effective database).",
    )
    return parser.parse_args(argv)


def default_db_path() -> Path:
    """Resolve the app's SQLite file without importing app singletons."""
    try:
        from src.core.config import settings  # noqa: PLC0415 - CLI startup
    except ImportError as exc:
        raise SystemExit(f"ABORT: cannot load settings: {exc}") from exc
    url = settings.effective_database_url
    if not url.startswith("sqlite:///"):
        raise SystemExit(
            "ABORT: quota_report reads local SQLite files only; "
            f"effective database is {url.split('://', 1)[0]}://…"
        )
    return Path(url.removeprefix("sqlite:///"))


def today_str(now: datetime) -> str:
    """UTC day key matching the quota_usage table (YYYY-MM-DD)."""
    return now.date().isoformat()


def time_until_reset(now: datetime) -> timedelta:
    """Time left until the daily window resets at UTC midnight."""
    midnight = datetime.combine(
        now.date() + timedelta(days=1), datetime.min.time(), tzinfo=timezone.utc
    )
    return midnight - now


def format_duration(delta: timedelta) -> str:
    """H:MM:SS countdown (never negative)."""
    total = max(0, int(delta.total_seconds()))
    hours, rest = divmod(total, 3600)
    minutes, seconds = divmod(rest, 60)
    return f"{hours}:{minutes:02d}:{seconds:02d}"


def read_today_rows(db_path: Path, day: str) -> list[tuple[str, str, int, int]]:
    """(provider, model, calls, tokens) for one day; [] when unavailable.

    Older databases predate the model_id column: fall back to
    per-provider rows labelled "(account)". A missing file/table is an
    empty report, never a crash.
    """
    if not db_path.is_file():
        return []
    try:
        connection = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
    except sqlite3.Error:
        return []
    try:
        try:
            rows = connection.execute(
                "SELECT provider, model_id, SUM(count), SUM(tokens) "
                "FROM quota_usage WHERE day = ? "
                "GROUP BY provider, model_id ORDER BY provider, model_id",
                (day,),
            ).fetchall()
        except sqlite3.Error:
            # Pre-migration table without model_id: per-provider totals.
            try:
                rows = [
                    (provider, "(account)", count, tokens)
                    for provider, count, tokens in connection.execute(
                        "SELECT provider, SUM(count), SUM(tokens) "
                        "FROM quota_usage WHERE day = ? GROUP BY provider "
                        "ORDER BY provider",
                        (day,),
                    ).fetchall()
                ]
            except sqlite3.Error:
                return []
    finally:
        connection.close()
    result: list[tuple[str, str, int, int]] = []
    for provider, model_id, count, tokens in rows:
        model = str(model_id or "") or "(account)"
        result.append((str(provider), model, int(count or 0), int(tokens or 0)))
    return result


def render(
    rows: list[tuple[str, str, int, int]], now: datetime
) -> tuple[str, int, int]:
    """Printable table + (total calls, total tokens)."""
    lines = [
        "provider             model                          calls   tokens",
        "-" * 70,
    ]
    total_calls = 0
    total_tokens = 0
    for provider, model, count, tokens in rows:
        total_calls += count
        total_tokens += tokens
        lines.append(f"{provider:<20} {model[:28]:<28} {count:>5} {tokens:>8}")
    lines.append("-" * 70)
    lines.append(
        f"TOTAL{'':<48} {total_calls:>5} {total_tokens:>8}   "
        f"(day {today_str(now)} UTC, resets in {format_duration(time_until_reset(now))})"
    )
    return "\n".join(lines), total_calls, total_tokens


def main(argv: list[str] | None = None) -> int:
    """CLI entry: resolve DB, print today's usage. Returns exit code."""
    args = parse_args(argv)
    try:
        db_path = args.db if args.db is not None else default_db_path()
    except SystemExit as exc:
        print(exc)
        return 2
    now = datetime.now(timezone.utc)
    rows = read_today_rows(db_path, today_str(now))
    if not rows:
        print(f"No quota usage recorded for {today_str(now)} UTC ({db_path}).")
        print(f"Daily window resets in {format_duration(time_until_reset(now))}.")
        return 0
    table, _, _ = render(rows, now)
    print(table)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
