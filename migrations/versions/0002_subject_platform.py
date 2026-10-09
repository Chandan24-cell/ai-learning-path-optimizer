"""Add subject content, enrollment, roles, and subject-scoped progress."""

from __future__ import annotations

import json

import sqlalchemy as sa
from alembic import op
from sqlalchemy import inspect

revision = "0002_subjects"
down_revision = "0001_initial"
branch_labels = None
depends_on = None

MATH_TOPIC_IDS = [
    "mathematics.algebra",
    "mathematics.geometry",
    "mathematics.probability",
    "mathematics.calculus",
    "mathematics.statistics",
    "mathematics.linear-algebra",
]


def _table_names() -> set[str]:
    return set(inspect(op.get_bind()).get_table_names())


def _column_names(table: str) -> set[str]:
    return {column["name"] for column in inspect(op.get_bind()).get_columns(table)}


def _create_content_tables() -> None:
    tables = _table_names()
    if "subjects" not in tables:
        op.create_table(
            "subjects",
            sa.Column("id", sa.String(80), primary_key=True),
            sa.Column("name", sa.String(120), nullable=False, unique=True),
            sa.Column("description", sa.Text(), nullable=False, server_default=""),
            sa.Column(
                "questions_status",
                sa.String(80),
                nullable=False,
                server_default="draft; teacher review required",
            ),
        )
    if "topics" not in tables:
        op.create_table(
            "topics",
            sa.Column("id", sa.String(160), primary_key=True),
            sa.Column("subject_id", sa.String(80), sa.ForeignKey("subjects.id"), nullable=False),
            sa.Column("slug", sa.String(80), nullable=False),
            sa.Column("name", sa.String(160), nullable=False),
            sa.Column("order", sa.Integer(), nullable=False),
        )
        op.create_index("ix_topics_subject_id", "topics", ["subject_id"])
    if "topic_prerequisites" not in tables:
        op.create_table(
            "topic_prerequisites",
            sa.Column("topic_id", sa.String(160), sa.ForeignKey("topics.id"), primary_key=True),
            sa.Column(
                "prerequisite_topic_id",
                sa.String(160),
                sa.ForeignKey("topics.id"),
                primary_key=True,
            ),
        )
    if "resources" not in tables:
        op.create_table(
            "resources",
            sa.Column("id", sa.String(180), primary_key=True),
            sa.Column("topic_id", sa.String(160), sa.ForeignKey("topics.id"), nullable=False),
            sa.Column("type", sa.String(40), nullable=False),
            sa.Column("title", sa.String(200), nullable=False),
            sa.Column("difficulty", sa.Float(), nullable=False),
            sa.Column("duration", sa.Float(), nullable=False),
            sa.Column("url", sa.Text()),
            sa.Column("body", sa.Text()),
        )
        op.create_index("ix_resources_topic_id", "resources", ["topic_id"])
    if "questions" not in tables:
        op.create_table(
            "questions",
            sa.Column("id", sa.String(180), primary_key=True),
            sa.Column("topic_id", sa.String(160), sa.ForeignKey("topics.id"), nullable=False),
            sa.Column("difficulty", sa.Float(), nullable=False),
            sa.Column("text", sa.Text(), nullable=False),
            sa.Column("options_json", sa.Text(), nullable=False),
            sa.Column("correct_option", sa.Integer(), nullable=False),
            sa.Column("explanation", sa.Text(), nullable=False),
            sa.Column("diagnostic", sa.Boolean(), nullable=False, server_default=sa.false()),
        )
        op.create_index("ix_questions_topic_id", "questions", ["topic_id"])
    if "enrollments" not in tables:
        op.create_table(
            "enrollments",
            sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id"), primary_key=True),
            sa.Column("subject_id", sa.String(80), sa.ForeignKey("subjects.id"), primary_key=True),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
            sa.Column(
                "diagnostic_completed", sa.Boolean(), nullable=False, server_default=sa.false()
            ),
        )


def _keyed_json(raw: str | None, default: object, ids: list[str]) -> str:
    value = json.loads(raw) if raw else default
    if isinstance(value, dict):
        return json.dumps(value)
    if isinstance(value, list):
        return json.dumps(
            {topic_id: value[index] for index, topic_id in enumerate(ids[: len(value)])}
        )
    return json.dumps({})


def _migrate_student_states() -> None:
    tables = _table_names()
    columns = _column_names("student_states") if "student_states" in tables else set()
    if "student_states" not in tables:
        op.create_table(
            "student_states",
            sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id"), primary_key=True),
            sa.Column("subject_id", sa.String(80), sa.ForeignKey("subjects.id"), primary_key=True),
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
        return
    if "subject_id" in columns:
        return

    connection = op.get_bind()
    legacy_rows = connection.execute(sa.text("SELECT * FROM student_states")).mappings().all()
    new_table = op.create_table(
        "student_states_phase_m",
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id"), primary_key=True),
        sa.Column("subject_id", sa.String(80), sa.ForeignKey("subjects.id"), primary_key=True),
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
    for row in legacy_rows:
        values = dict(row)
        values["subject_id"] = "mathematics"
        values["mastery_est_json"] = _keyed_json(
            values.get("mastery_est_json"), [0.25] * 6, MATH_TOPIC_IDS
        )
        values["attempts_json"] = _keyed_json(values.get("attempts_json"), [0] * 6, MATH_TOPIC_IDS)
        connection.execute(new_table.insert(), [values])

    op.drop_table("student_states")
    op.rename_table("student_states_phase_m", "student_states")


def upgrade() -> None:
    tables = _table_names()
    if "users" not in tables:
        raise RuntimeError("The users table must exist before the subject migration")

    if "role" not in _column_names("users"):
        op.add_column(
            "users",
            sa.Column("role", sa.String(16), nullable=False, server_default="student"),
        )

    _create_content_tables()
    connection = op.get_bind()
    subject_exists = connection.execute(
        sa.text("SELECT 1 FROM subjects WHERE id = :subject_id"), {"subject_id": "mathematics"}
    ).first()
    if subject_exists is None:
        connection.execute(
            sa.text(
                "INSERT INTO subjects (id, name, description, questions_status) "
                "VALUES ('mathematics', 'Mathematics', "
                "'Foundational mathematics topics migrated from the original project.', "
                "'draft; teacher review required')"
            )
        )

    if "active_subject_id" not in _column_names("users"):
        op.add_column(
            "users",
            sa.Column("active_subject_id", sa.String(80)),
        )

    _migrate_student_states()

    if "subject_id" not in _column_names("interactions"):
        with op.batch_alter_table("interactions") as batch:
            batch.add_column(
                sa.Column(
                    "subject_id",
                    sa.String(80),
                    sa.ForeignKey(
                        "subjects.id",
                        name="fk_interactions_subject_id_subjects",
                    ),
                    nullable=False,
                    server_default="mathematics",
                )
            )
    if "resource_id" not in _column_names("interactions"):
        op.add_column("interactions", sa.Column("resource_id", sa.String(180)))

    connection.execute(
        sa.text(
            "INSERT INTO enrollments (user_id, subject_id, diagnostic_completed) "
            "SELECT id, 'mathematics', TRUE FROM users WHERE 1=1 "
            "ON CONFLICT (user_id, subject_id) DO NOTHING"
        )
    )
    connection.execute(
        sa.text(
            "UPDATE users SET active_subject_id = 'mathematics' WHERE active_subject_id IS NULL"
        )
    )
    connection.exec_driver_sql(
        """INSERT INTO student_states
        (user_id, subject_id, ability, motivation, mastery_est_json, attempts_json,
         recent_scores_json, total_time_min, engagement_ma, last_difficulty, last_score,
         n_interactions)
        SELECT u.id, 'mathematics', 0.0, 0.6,
               '{"mathematics.algebra":0.25,"mathematics.geometry":0.25,
                 "mathematics.probability":0.25,"mathematics.calculus":0.25,
                 "mathematics.statistics":0.25,"mathematics.linear-algebra":0.25}',
               '{"mathematics.algebra":0,"mathematics.geometry":0,
                 "mathematics.probability":0,"mathematics.calculus":0,
                 "mathematics.statistics":0,"mathematics.linear-algebra":0}',
               '[]', 0.0, 0.5, 3.0, 50.0, 0
        FROM users u
        WHERE NOT EXISTS (
            SELECT 1 FROM student_states s
            WHERE s.user_id = u.id AND s.subject_id = 'mathematics'
        )
        ON CONFLICT (user_id, subject_id) DO NOTHING"""
    )


def downgrade() -> None:
    # User progress and content are retained; downgrade only removes the new schema is unsafe.
    raise RuntimeError("The subject platform migration is intentionally non-reversible")
