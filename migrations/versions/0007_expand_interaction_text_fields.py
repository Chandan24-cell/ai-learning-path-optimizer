"""Expand interaction identifiers to support longer topic and resource IDs."""

from alembic import op
import sqlalchemy as sa

revision = "0007_interaction_lengths"
down_revision = "0006_rule_based_quizzes"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("interactions") as batch:
        batch.alter_column(
            "topic",
            existing_type=sa.String(length=32),
            type_=sa.String(length=160),
            existing_nullable=True,
        )
        batch.alter_column(
            "resource_id",
            existing_type=sa.String(length=32),
            type_=sa.String(length=180),
            existing_nullable=True,
        )


def downgrade() -> None:
    raise RuntimeError(
        "Downgrade is disabled to prevent data truncation."
    )
