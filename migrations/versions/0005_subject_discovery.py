"""Add subject provenance and enrollment path settings."""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0005_subject_discovery"
down_revision = "0004_learner_profiles"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("subjects") as batch:
        batch.add_column(
            sa.Column("source", sa.String(length=16), nullable=False, server_default="pack")
        )
        batch.add_column(
            sa.Column("status", sa.String(length=16), nullable=False, server_default="draft")
        )
        batch.add_column(sa.Column("created_by", sa.Integer(), nullable=True))
        batch.add_column(sa.Column("source_url", sa.Text(), nullable=True))
        batch.add_column(sa.Column("retrieved_at", sa.DateTime(timezone=True), nullable=True))
        batch.add_column(sa.Column("reference_book", sa.Text(), nullable=True))
    with op.batch_alter_table("topics") as batch:
        batch.add_column(sa.Column("source_url", sa.Text(), nullable=True))
        batch.add_column(sa.Column("retrieved_at", sa.DateTime(timezone=True), nullable=True))
        batch.add_column(sa.Column("provenance", sa.Text(), nullable=True))
    with op.batch_alter_table("resources") as batch:
        batch.add_column(sa.Column("source_url", sa.Text(), nullable=True))
        batch.add_column(sa.Column("retrieved_at", sa.DateTime(timezone=True), nullable=True))
        batch.add_column(sa.Column("provenance", sa.Text(), nullable=True))
    with op.batch_alter_table("enrollments") as batch:
        batch.add_column(sa.Column("education_level_used", sa.String(length=40), nullable=True))
        batch.add_column(
            sa.Column(
                "target_depth", sa.String(length=16), nullable=False, server_default="beginner"
            )
        )
        batch.add_column(sa.Column("reference_book", sa.Text(), nullable=True))
    with op.batch_alter_table("student_states") as batch:
        batch.add_column(
            sa.Column("self_ratings_json", sa.Text(), nullable=True, server_default="{}")
        )


def downgrade() -> None:
    with op.batch_alter_table("student_states") as batch:
        batch.drop_column("self_ratings_json")
    with op.batch_alter_table("enrollments") as batch:
        batch.drop_column("reference_book")
        batch.drop_column("target_depth")
        batch.drop_column("education_level_used")
    with op.batch_alter_table("resources") as batch:
        batch.drop_column("provenance")
        batch.drop_column("retrieved_at")
        batch.drop_column("source_url")
    with op.batch_alter_table("topics") as batch:
        batch.drop_column("provenance")
        batch.drop_column("retrieved_at")
        batch.drop_column("source_url")
    with op.batch_alter_table("subjects") as batch:
        batch.drop_column("reference_book")
        batch.drop_column("retrieved_at")
        batch.drop_column("source_url")
        batch.drop_column("created_by")
        batch.drop_column("status")
        batch.drop_column("source")
