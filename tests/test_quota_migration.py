"""quota_usage model-scope migration: upgrade/downgrade on throwaway SQLite.

Runs the real revision upgrade()/downgrade() functions (no network, no
repo database) and asserts schema + data behavior. Key material never
appears: rows carry only salted fingerprints, scanned at the end.
"""

import importlib.util
from pathlib import Path

import sqlalchemy as sa
from sqlalchemy import create_engine, inspect, text

PROJECT_ROOT = Path(__file__).resolve().parent.parent
VERSIONS = PROJECT_ROOT / "alembic" / "versions"


def _load_revision(alias: str, filename: str):
    spec = importlib.util.spec_from_file_location(alias, VERSIONS / filename)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


BASELINE = _load_revision("baseline_rev", "db244319c60b_baseline.py")
SCOPE = _load_revision("scope_rev", "c41a9e2f7b3d_quota_model_scope.py")


def _run(direction: str, conn) -> None:
    """Run one revision function with the op proxy bound to conn."""
    from alembic.migration import MigrationContext
    from alembic.operations import Operations

    ctx = MigrationContext.configure(conn)
    with Operations.context(ctx):
        if direction == "up":
            SCOPE.upgrade()
        else:
            SCOPE.downgrade()


def _quota_columns(conn) -> list[str]:
    return [col["name"] for col in inspect(conn).get_columns("quota_usage")]


def _quota_pk(conn) -> list[str]:
    pk = inspect(conn).get_pk_constraint("quota_usage")
    return list(pk.get("constrained_columns") or [])


def test_revision_chain() -> None:
    assert SCOPE.down_revision == BASELINE.revision
    assert SCOPE.revision != BASELINE.revision


def test_upgrade_preserves_rows_as_account_bucket(tmp_path) -> None:
    engine = create_engine(f"sqlite:///{tmp_path}/mig.db")
    with engine.begin() as conn:
        conn.execute(
            text(
                "CREATE TABLE quota_usage (provider VARCHAR NOT NULL, "
                "key_fingerprint VARCHAR NOT NULL, day VARCHAR NOT NULL, "
                "count INTEGER, tokens INTEGER, updated_at DATETIME, "
                "PRIMARY KEY (provider, key_fingerprint, day))"
            )
        )
        conn.execute(
            text(
                "INSERT INTO quota_usage "
                "(provider, key_fingerprint, day, count, tokens) "
                "VALUES ('groq', 'fp1', '2026-10-09', 7, 700)"
            )
        )
        _run("up", conn)
        assert "model_id" in _quota_columns(conn)
        assert _quota_pk(conn) == [
            "provider",
            "key_fingerprint",
            "day",
            "model_id",
        ]
        row = conn.execute(text("SELECT * FROM quota_usage")).mappings().one()
        assert (row["count"], row["tokens"], row["model_id"]) == (7, 700, "")
        # New per-model rows coexist with the account row.
        conn.execute(
            text(
                "INSERT INTO quota_usage "
                "(provider, key_fingerprint, day, model_id, count, tokens) "
                "VALUES ('groq', 'fp1', '2026-10-09', 'openai/gpt-oss-20b', 2, 200)"
            )
        )
        assert conn.execute(text("SELECT COUNT(*) FROM quota_usage")).scalar() == 2


def test_downgrade_keeps_account_rows_only(tmp_path) -> None:
    engine = create_engine(f"sqlite:///{tmp_path}/mig.db")
    with engine.begin() as conn:
        conn.execute(
            text(
                "CREATE TABLE quota_usage (provider VARCHAR NOT NULL, "
                "key_fingerprint VARCHAR NOT NULL, day VARCHAR NOT NULL, "
                "model_id VARCHAR NOT NULL DEFAULT '', "
                "count INTEGER, tokens INTEGER, updated_at DATETIME, "
                "PRIMARY KEY (provider, key_fingerprint, day, model_id))"
            )
        )
        conn.execute(
            text(
                "INSERT INTO quota_usage "
                "(provider, key_fingerprint, day, model_id, count, tokens) "
                "VALUES ('groq', 'fp1', '2026-10-09', '', 7, 700), "
                "('groq', 'fp1', '2026-10-09', 'openai/gpt-oss-20b', 2, 200)"
            )
        )
        _run("down", conn)
        assert "model_id" not in _quota_columns(conn)
        assert _quota_pk(conn) == ["provider", "key_fingerprint", "day"]
        rows = conn.execute(text("SELECT * FROM quota_usage")).mappings().all()
        assert len(rows) == 1  # ephemeral per-model counters are dropped
        assert (rows[0]["count"], rows[0]["tokens"]) == (7, 700)


def test_migration_touches_no_keys(tmp_path, fake_key: str) -> None:
    """Only fingerprints may land in quota rows — never raw key material."""
    from src.providers.quota import fingerprint_key

    engine = create_engine(f"sqlite:///{tmp_path}/mig.db")
    fingerprint = fingerprint_key(fake_key)
    with engine.begin() as conn:
        conn.execute(
            text(
                "CREATE TABLE quota_usage (provider VARCHAR NOT NULL, "
                "key_fingerprint VARCHAR NOT NULL, day VARCHAR NOT NULL, "
                "count INTEGER, tokens INTEGER, updated_at DATETIME, "
                "PRIMARY KEY (provider, key_fingerprint, day))"
            )
        )
        conn.execute(
            text(
                "INSERT INTO quota_usage "
                "(provider, key_fingerprint, day, count, tokens) "
                "VALUES ('groq', :fp, '2026-10-09', 1, 10)"
            ),
            {"fp": fingerprint},
        )
        _run("up", conn)
        blob = " ".join(
            str(row) for row in conn.execute(text("SELECT * FROM quota_usage")).all()
        )
    assert fake_key not in blob
    assert fingerprint in blob
    assert "quota_usage" in [t for t in inspect(engine).get_table_names()]
    assert sa is not None  # sqlalchemy wiring intact
