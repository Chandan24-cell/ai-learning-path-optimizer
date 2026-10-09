"""Add onboarding profiles and per-subject learner levels."""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0004_learner_profiles"
down_revision = "0003_interaction_history"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "learner_profiles",
        sa.Column(
            "user_id",
            sa.Integer(),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column("country", sa.String(length=120), nullable=False),
        sa.Column("language", sa.String(length=80), nullable=False),
        sa.Column("education_level", sa.String(length=40), nullable=False),
        sa.Column("institution_type", sa.String(length=40), nullable=False),
        sa.Column("grade_year", sa.String(length=80), nullable=False),
        sa.Column("curriculum_program", sa.String(length=120)),
        sa.Column("field_of_study", sa.String(length=120), nullable=False),
        sa.Column("learning_goal", sa.String(length=24), nullable=False),
        sa.Column("weekly_time_hours", sa.Float(), nullable=False),
        sa.Column("learning_style", sa.String(length=24), nullable=False),
        sa.Column("prior_experience", sa.String(length=24), nullable=False),
        sa.Column("consent_version", sa.String(length=32), nullable=False),
        sa.Column("consent_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    with op.batch_alter_table("student_states") as batch:
        batch.add_column(
            sa.Column("learner_level", sa.Float(), nullable=False, server_default="25.0")
        )
        batch.add_column(
            sa.Column(
                "learner_level_label",
                sa.String(length=40),
                nullable=False,
                server_default="middle_school",
            )
        )
        batch.add_column(
            sa.Column("learning_goal", sa.String(length=24), nullable=False, server_default="skill")
        )


def downgrade() -> None:
    with op.batch_alter_table("student_states") as batch:
        batch.drop_column("learning_goal")
        batch.drop_column("learner_level_label")
        batch.drop_column("learner_level")
    op.drop_table("learner_profiles")
