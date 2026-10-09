"""quota model scope

Revision ID: c41a9e2f7b3d
Revises: db244319c60b
Create Date: 2026-10-09

Per-model + account-scope daily counters: quota_usage gains model_id
(catalog model id, or "" for the shared account-scope bucket) as part of
the primary key. SQLite cannot alter a PK in place, so both directions
rebuild the table explicitly. Upgrade preserves every row (old rows
become account-bucket rows); downgrade keeps account rows only —
per-model counters are ephemeral free-tier windows, documented here.
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "c41a9e2f7b3d"
down_revision: str | None = "db244319c60b"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "quota_usage_new",
        sa.Column("provider", sa.String(), nullable=False),
        sa.Column("key_fingerprint", sa.String(), nullable=False),
        sa.Column("day", sa.String(), nullable=False),
        sa.Column("model_id", sa.String(), nullable=False, server_default=""),
        sa.Column("count", sa.Integer(), nullable=True),
        sa.Column("tokens", sa.Integer(), nullable=True),
        sa.Column("updated_at", sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint("provider", "key_fingerprint", "day", "model_id"),
    )
    op.execute(
        "INSERT INTO quota_usage_new "
        "(provider, key_fingerprint, day, model_id, count, tokens, updated_at) "
        "SELECT provider, key_fingerprint, day, '', count, tokens, updated_at "
        "FROM quota_usage"
    )
    op.drop_table("quota_usage")
    op.rename_table("quota_usage_new", "quota_usage")


def downgrade() -> None:
    op.create_table(
        "quota_usage_old",
        sa.Column("provider", sa.String(), nullable=False),
        sa.Column("key_fingerprint", sa.String(), nullable=False),
        sa.Column("day", sa.String(), nullable=False),
        sa.Column("count", sa.Integer(), nullable=True),
        sa.Column("tokens", sa.Integer(), nullable=True),
        sa.Column("updated_at", sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint("provider", "key_fingerprint", "day"),
    )
    op.execute(
        "INSERT INTO quota_usage_old "
        "(provider, key_fingerprint, day, count, tokens, updated_at) "
        "SELECT provider, key_fingerprint, day, count, tokens, updated_at "
        "FROM quota_usage WHERE model_id = ''"
    )
    op.drop_table("quota_usage")
    op.rename_table("quota_usage_old", "quota_usage")
