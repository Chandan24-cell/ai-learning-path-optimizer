"""Add cited generated questions, adaptive quiz history, and question reports."""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0006_rule_based_quizzes"
down_revision = "0005_subject_discovery"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("topics") as batch:
        batch.add_column(sa.Column("source_extract", sa.Text(), nullable=True))
        batch.add_column(
            sa.Column(
                "quiz_status",
                sa.String(length=24),
                nullable=False,
                server_default="not_generated",
            )
        )
    with op.batch_alter_table("questions") as batch:
        batch.add_column(sa.Column("question_type", sa.String(length=32), nullable=True))
        batch.add_column(sa.Column("source_sentence", sa.Text(), nullable=True))
        batch.add_column(sa.Column("source_url", sa.Text(), nullable=True))
        batch.add_column(sa.Column("attribution", sa.String(length=160), nullable=True))
        batch.add_column(sa.Column("generated_at", sa.DateTime(timezone=True), nullable=True))
        batch.add_column(sa.Column("generator_version", sa.String(length=40), nullable=True))
        batch.add_column(sa.Column("status", sa.String(length=80), nullable=True))

    op.create_table(
        "question_sessions",
        sa.Column("id", sa.String(length=80), primary_key=True),
        sa.Column(
            "user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False
        ),
        sa.Column(
            "subject_id",
            sa.String(length=80),
            sa.ForeignKey("subjects.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "topic_id",
            sa.String(length=160),
            sa.ForeignKey("topics.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("resource_id", sa.String(length=180), nullable=False),
        sa.Column("mode", sa.String(length=16), nullable=False, server_default="activity"),
        sa.Column("max_questions", sa.Integer(), nullable=False),
        sa.Column("asked_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("correct_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("reused_questions", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("prerequisite_focus", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("started_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("completed_at", sa.DateTime(timezone=True)),
    )
    op.create_index("ix_question_sessions_user_id", "question_sessions", ["user_id"])

    op.create_table(
        "question_exposures",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False
        ),
        sa.Column(
            "subject_id",
            sa.String(length=80),
            sa.ForeignKey("subjects.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "topic_id",
            sa.String(length=160),
            sa.ForeignKey("topics.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "question_id",
            sa.String(length=180),
            sa.ForeignKey("questions.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "session_id",
            sa.String(length=80),
            sa.ForeignKey("question_sessions.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "seen_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column("answered_at", sa.DateTime(timezone=True)),
        sa.Column("answer_index", sa.Integer()),
        sa.Column("is_correct", sa.Boolean()),
        sa.UniqueConstraint("session_id", "question_id", name="uq_question_exposure_session"),
    )
    op.create_index(
        "ix_question_exposures_user_question", "question_exposures", ["user_id", "question_id"]
    )

    op.create_table(
        "question_reports",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False
        ),
        sa.Column(
            "question_id",
            sa.String(length=180),
            sa.ForeignKey("questions.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("reason", sa.String(length=32), nullable=False),
        sa.Column("details", sa.String(length=500)),
        sa.Column("status", sa.String(length=16), nullable=False, server_default="open"),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column("reviewed_by", sa.Integer(), sa.ForeignKey("users.id")),
        sa.Column("reviewed_at", sa.DateTime(timezone=True)),
    )
    op.create_index("ix_question_reports_user_id", "question_reports", ["user_id"])
    op.create_index("ix_question_reports_question_id", "question_reports", ["question_id"])


def downgrade() -> None:
    op.drop_index("ix_question_reports_question_id", table_name="question_reports")
    op.drop_index("ix_question_reports_user_id", table_name="question_reports")
    op.drop_table("question_reports")
    op.drop_index("ix_question_exposures_user_question", table_name="question_exposures")
    op.drop_table("question_exposures")
    op.drop_index("ix_question_sessions_user_id", table_name="question_sessions")
    op.drop_table("question_sessions")
    with op.batch_alter_table("questions") as batch:
        batch.drop_column("status")
        batch.drop_column("generator_version")
        batch.drop_column("generated_at")
        batch.drop_column("attribution")
        batch.drop_column("source_url")
        batch.drop_column("source_sentence")
        batch.drop_column("question_type")
    with op.batch_alter_table("topics") as batch:
        batch.drop_column("quiz_status")
        batch.drop_column("source_extract")
