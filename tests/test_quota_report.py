"""Offline tests for scripts/quota_report.py (tmp SQLite, no network/keys)."""

import sqlite3
from datetime import datetime, timedelta, timezone

from scripts.quota_report import (
    format_duration,
    read_today_rows,
    render,
    time_until_reset,
)


def _seed(db_path, rows, with_model=True) -> None:
    connection = sqlite3.connect(db_path)
    try:
        if with_model:
            connection.execute(
                "CREATE TABLE quota_usage (provider TEXT, key_fingerprint TEXT, "
                "day TEXT, model_id TEXT, count INTEGER, tokens INTEGER)"
            )
            connection.executemany(
                "INSERT INTO quota_usage VALUES (?, ?, ?, ?, ?, ?)", rows
            )
        else:
            connection.execute(
                "CREATE TABLE quota_usage (provider TEXT, key_fingerprint TEXT, "
                "day TEXT, count INTEGER, tokens INTEGER)"
            )
            connection.executemany(
                "INSERT INTO quota_usage VALUES (?, ?, ?, ?, ?)", rows
            )
        connection.commit()
    finally:
        connection.close()


def test_read_aggregates_per_model_without_fingerprints(tmp_path) -> None:
    db = tmp_path / "q.db"
    _seed(
        db,
        [
            ("groq", "fp1", "2026-10-09", "openai/gpt-oss-20b", 3, 100),
            ("groq", "fp2", "2026-10-09", "openai/gpt-oss-20b", 2, 50),
            ("groq", "fp1", "2026-10-09", "", 1, 10),
            ("gemini", "fp9", "2026-10-08", "gemini-3.8-flash", 9, 900),
        ],
    )
    rows = read_today_rows(db, "2026-10-09")
    assert ("groq", "openai/gpt-oss-20b", 5, 150) in rows
    assert ("groq", "(account)", 1, 10) in rows
    blob = str(rows)
    assert "fp1" not in blob and "fp2" not in blob and "fp9" not in blob
    assert len(rows) == 2  # yesterday's row excluded


def test_read_falls_back_without_model_id(tmp_path) -> None:
    db = tmp_path / "old.db"
    _seed(db, [("groq", "fp1", "2026-10-09", 4, 40)], with_model=False)
    assert read_today_rows(db, "2026-10-09") == [("groq", "(account)", 4, 40)]


def test_read_missing_db_is_empty(tmp_path) -> None:
    assert read_today_rows(tmp_path / "nope.db", "2026-10-09") == []


def test_render_totals_and_countdown() -> None:
    now = datetime(2026, 10, 9, 12, 0, tzinfo=timezone.utc)
    table, calls, tokens = render([("groq", "m", 5, 150)], now)
    assert calls == 5 and tokens == 150
    assert "groq" in table and "150" in table
    assert format_duration(time_until_reset(now)) == "12:00:00"
    assert timedelta(0) < time_until_reset(now) <= timedelta(hours=24)
