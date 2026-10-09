"""Index subject-scoped interaction history queries."""

from __future__ import annotations

from alembic import op

revision = "0003_interaction_history"
down_revision = "0002_subjects"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_index(
        "ix_interactions_user_subject_id",
        "interactions",
        ["user_id", "subject_id", "id"],
    )


def downgrade() -> None:
    op.drop_index("ix_interactions_user_subject_id", table_name="interactions")
