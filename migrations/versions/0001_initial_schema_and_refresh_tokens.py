"""Create app tables and refresh-token storage; safe for existing SQLite data."""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy import inspect

revision = "0001_initial"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = inspect(bind)
    tables = set(inspector.get_table_names())

    if "users" not in tables:
        op.create_table(
            "users",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("username", sa.String(length=64), nullable=False),
            sa.Column("hashed_password", sa.String(length=255), nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        )
    if "student_states" not in tables:
        op.create_table(
            "student_states",
            sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id"), primary_key=True),
            sa.Column("ability", sa.Float()),
            sa.Column("motivation", sa.Float()),
            sa.Column("mastery_est_json", sa.Text()),
            sa.Column("attempts_json", sa.Text()),
            sa.Column("recent_scores_json", sa.Text()),
            sa.Column("total_time_min", sa.Float()),
            sa.Column("engagement_ma", sa.Float()),
            sa.Column("last_difficulty", sa.Float()),
            sa.Column("last_score", sa.Float()),
            sa.Column("n_interactions", sa.Integer()),
        )
    if "interactions" not in tables:
        op.create_table(
            "interactions",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id")),
            sa.Column("timestamp", sa.DateTime(timezone=True), server_default=sa.func.now()),
            sa.Column("action", sa.Integer()),
            sa.Column("topic", sa.String(length=32)),
            sa.Column("rtype", sa.String(length=32)),
            sa.Column("difficulty", sa.Float()),
            sa.Column("duration", sa.Float()),
            sa.Column("score", sa.Float()),
            sa.Column("gain", sa.Float()),
            sa.Column("engagement", sa.Float()),
        )
    if "refresh_tokens" not in tables:
        op.create_table(
            "refresh_tokens",
            sa.Column("id", sa.String(length=128), primary_key=True),
            sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
            sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("revoked", sa.Boolean(), nullable=False, server_default=sa.false()),
        )

    inspector = inspect(bind)
    indexes = {
        (table, index["name"])
        for table in inspector.get_table_names()
        for index in inspector.get_indexes(table)
    }
    if ("users", "ix_users_username") not in indexes:
        op.create_index("ix_users_username", "users", ["username"], unique=True)
    if ("interactions", "ix_interactions_user_id") not in indexes:
        op.create_index("ix_interactions_user_id", "interactions", ["user_id"])
    if ("refresh_tokens", "ix_refresh_tokens_user_id") not in indexes:
        op.create_index("ix_refresh_tokens_user_id", "refresh_tokens", ["user_id"])


def downgrade() -> None:
    # This initial migration may be stamped onto an existing live database.
    # Keeping downgrade non-destructive avoids dropping users' existing data.
    pass
