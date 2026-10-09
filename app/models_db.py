"""ORM models for accounts, subject content, enrollment, progress, and history."""

from __future__ import annotations

import json
from datetime import datetime
from typing import cast

from sqlalchemy import (
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func

from app.database import Base

DEFAULT_MASTERY = 0.25


class User(Base):
    __tablename__ = "users"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    username: Mapped[str] = mapped_column(String(64), unique=True, index=True, nullable=False)
    hashed_password: Mapped[str] = mapped_column(String(255), nullable=False)
    role: Mapped[str] = mapped_column(String(16), nullable=False, default="student")
    active_subject_id: Mapped[str | None] = mapped_column(String(80))
    created_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class LearnerProfile(Base):
    __tablename__ = "learner_profiles"

    user_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("users.id", ondelete="CASCADE"), primary_key=True
    )
    country: Mapped[str] = mapped_column(String(120), nullable=False)
    language: Mapped[str] = mapped_column(String(80), nullable=False)
    education_level: Mapped[str] = mapped_column(String(40), nullable=False)
    institution_type: Mapped[str] = mapped_column(String(40), nullable=False)
    grade_year: Mapped[str] = mapped_column(String(80), nullable=False)
    curriculum_program: Mapped[str | None] = mapped_column(String(120))
    field_of_study: Mapped[str] = mapped_column(String(120), nullable=False)
    learning_goal: Mapped[str] = mapped_column(String(24), nullable=False)
    weekly_time_hours: Mapped[float] = mapped_column(Float, nullable=False)
    learning_style: Mapped[str] = mapped_column(String(24), nullable=False)
    prior_experience: Mapped[str] = mapped_column(String(24), nullable=False)
    consent_version: Mapped[str] = mapped_column(String(32), nullable=False)
    consent_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class Subject(Base):
    __tablename__ = "subjects"
    id: Mapped[str] = mapped_column(String(80), primary_key=True)
    name: Mapped[str] = mapped_column(String(120), unique=True, nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False, default="")
    questions_status: Mapped[str] = mapped_column(
        String(80), nullable=False, default="draft; teacher review required"
    )
    source: Mapped[str] = mapped_column(String(16), nullable=False, default="pack")
    status: Mapped[str] = mapped_column(
        String(16), nullable=False, default="draft", server_default="draft"
    )
    created_by: Mapped[int | None] = mapped_column(Integer)
    source_url: Mapped[str | None] = mapped_column(Text)
    retrieved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    reference_book: Mapped[str | None] = mapped_column(Text)


class Topic(Base):
    __tablename__ = "topics"
    id: Mapped[str] = mapped_column(String(160), primary_key=True)
    subject_id: Mapped[str] = mapped_column(
        String(80), ForeignKey("subjects.id"), nullable=False, index=True
    )
    slug: Mapped[str] = mapped_column(String(80), nullable=False)
    name: Mapped[str] = mapped_column(String(160), nullable=False)
    order: Mapped[int] = mapped_column(Integer, nullable=False)
    source_url: Mapped[str | None] = mapped_column(Text)
    retrieved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    provenance: Mapped[str | None] = mapped_column(Text)
    source_extract: Mapped[str | None] = mapped_column(Text)
    quiz_status: Mapped[str] = mapped_column(
        String(24), nullable=False, default="not_generated", server_default="not_generated"
    )


class TopicPrerequisite(Base):
    __tablename__ = "topic_prerequisites"
    topic_id: Mapped[str] = mapped_column(String(160), ForeignKey("topics.id"), primary_key=True)
    prerequisite_topic_id: Mapped[str] = mapped_column(
        String(160), ForeignKey("topics.id"), primary_key=True
    )


class Resource(Base):
    __tablename__ = "resources"
    id: Mapped[str] = mapped_column(String(180), primary_key=True)
    topic_id: Mapped[str] = mapped_column(
        String(160), ForeignKey("topics.id"), nullable=False, index=True
    )
    type: Mapped[str] = mapped_column(String(40), nullable=False)
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    difficulty: Mapped[float] = mapped_column(Float, nullable=False)
    duration: Mapped[float] = mapped_column(Float, nullable=False)
    url: Mapped[str | None] = mapped_column(Text)
    body: Mapped[str | None] = mapped_column(Text)
    source_url: Mapped[str | None] = mapped_column(Text)
    retrieved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    provenance: Mapped[str | None] = mapped_column(Text)


class Question(Base):
    __tablename__ = "questions"
    id: Mapped[str] = mapped_column(String(180), primary_key=True)
    topic_id: Mapped[str] = mapped_column(
        String(160), ForeignKey("topics.id"), nullable=False, index=True
    )
    difficulty: Mapped[float] = mapped_column(Float, nullable=False)
    text: Mapped[str] = mapped_column(Text, nullable=False)
    options_json: Mapped[str] = mapped_column(Text, nullable=False)
    correct_option: Mapped[int] = mapped_column(Integer, nullable=False)
    explanation: Mapped[str] = mapped_column(Text, nullable=False)
    diagnostic: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    question_type: Mapped[str | None] = mapped_column(String(32))
    source_sentence: Mapped[str | None] = mapped_column(Text)
    source_url: Mapped[str | None] = mapped_column(Text)
    attribution: Mapped[str | None] = mapped_column(String(160))
    generated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    generator_version: Mapped[str | None] = mapped_column(String(40))
    status: Mapped[str | None] = mapped_column(String(80))

    @property
    def options(self) -> list[str]:
        return cast(list[str], json.loads(self.options_json))


class Enrollment(Base):
    __tablename__ = "enrollments"
    user_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id"), primary_key=True)
    subject_id: Mapped[str] = mapped_column(String(80), ForeignKey("subjects.id"), primary_key=True)
    created_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    diagnostic_completed: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    education_level_used: Mapped[str | None] = mapped_column(String(40))
    target_depth: Mapped[str] = mapped_column(String(16), nullable=False, default="beginner")
    reference_book: Mapped[str | None] = mapped_column(Text)


class StudentState(Base):
    __tablename__ = "student_states"
    user_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id"), primary_key=True)
    subject_id: Mapped[str] = mapped_column(String(80), ForeignKey("subjects.id"), primary_key=True)

    ability: Mapped[float | None] = mapped_column(Float, default=0.0)
    motivation: Mapped[float | None] = mapped_column(Float, default=0.6)
    learner_level: Mapped[float] = mapped_column(Float, nullable=False, default=25.0)
    learner_level_label: Mapped[str] = mapped_column(
        String(40), nullable=False, default="middle_school"
    )
    learning_goal: Mapped[str] = mapped_column(String(24), nullable=False, default="skill")
    mastery_est_json: Mapped[str | None] = mapped_column(Text, default="{}")
    attempts_json: Mapped[str | None] = mapped_column(Text, default="{}")
    recent_scores_json: Mapped[str | None] = mapped_column(Text, default="[]")
    self_ratings_json: Mapped[str | None] = mapped_column(Text, default="{}")
    total_time_min: Mapped[float | None] = mapped_column(Float, default=0.0)
    engagement_ma: Mapped[float | None] = mapped_column(Float, default=0.5)
    last_difficulty: Mapped[float | None] = mapped_column(Float, default=3.0)
    last_score: Mapped[float | None] = mapped_column(Float, default=50.0)
    n_interactions: Mapped[int | None] = mapped_column(Integer, default=0)

    @property
    def mastery_est(self) -> dict[str, float]:
        raw = json.loads(self.mastery_est_json or "{}")
        if isinstance(raw, list):
            return {str(index): float(value) for index, value in enumerate(raw)}
        return cast(dict[str, float], raw)

    @property
    def attempts(self) -> dict[str, int]:
        raw = json.loads(self.attempts_json or "{}")
        if isinstance(raw, list):
            return {str(index): int(value) for index, value in enumerate(raw)}
        return cast(dict[str, int], raw)

    @property
    def recent_scores(self) -> list[float]:
        return cast(list[float], json.loads(self.recent_scores_json or "[]"))


class Interaction(Base):
    __tablename__ = "interactions"
    __table_args__ = (Index("ix_interactions_user_subject_id", "user_id", "subject_id", "id"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("users.id"), index=True)
    subject_id: Mapped[str] = mapped_column(
        String(80), ForeignKey("subjects.id"), nullable=False, default="mathematics"
    )
    timestamp: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    action: Mapped[int | None] = mapped_column(Integer)
    resource_id: Mapped[str | None] = mapped_column(String(180))
    topic: Mapped[str | None] = mapped_column(String(160))
    rtype: Mapped[str | None] = mapped_column(String(32))
    difficulty: Mapped[float | None] = mapped_column(Float)
    duration: Mapped[float | None] = mapped_column(Float)
    score: Mapped[float | None] = mapped_column(Float)
    gain: Mapped[float | None] = mapped_column(Float)
    engagement: Mapped[float | None] = mapped_column(Float)


class RefreshToken(Base):
    __tablename__ = "refresh_tokens"
    id: Mapped[str] = mapped_column(String(128), primary_key=True)
    user_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("users.id"), index=True, nullable=False
    )
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    revoked: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)


class QuestionSession(Base):
    __tablename__ = "question_sessions"

    id: Mapped[str] = mapped_column(String(80), primary_key=True)
    user_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    subject_id: Mapped[str] = mapped_column(
        String(80), ForeignKey("subjects.id", ondelete="CASCADE"), nullable=False
    )
    topic_id: Mapped[str] = mapped_column(
        String(160), ForeignKey("topics.id", ondelete="CASCADE"), nullable=False
    )
    resource_id: Mapped[str] = mapped_column(String(180), nullable=False)
    mode: Mapped[str] = mapped_column(String(16), nullable=False, default="activity")
    max_questions: Mapped[int] = mapped_column(Integer, nullable=False)
    asked_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    correct_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    reused_questions: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    prerequisite_focus: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    started_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class QuestionExposure(Base):
    __tablename__ = "question_exposures"
    __table_args__ = (
        UniqueConstraint("session_id", "question_id", name="uq_question_exposure_session"),
        Index("ix_question_exposures_user_question", "user_id", "question_id"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    subject_id: Mapped[str] = mapped_column(
        String(80), ForeignKey("subjects.id", ondelete="CASCADE"), nullable=False
    )
    topic_id: Mapped[str] = mapped_column(
        String(160), ForeignKey("topics.id", ondelete="CASCADE"), nullable=False
    )
    question_id: Mapped[str] = mapped_column(
        String(180), ForeignKey("questions.id", ondelete="CASCADE"), nullable=False
    )
    session_id: Mapped[str] = mapped_column(
        String(80), ForeignKey("question_sessions.id", ondelete="CASCADE"), nullable=False
    )
    seen_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    answered_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    answer_index: Mapped[int | None] = mapped_column(Integer)
    is_correct: Mapped[bool | None] = mapped_column(Boolean)


class QuestionReport(Base):
    __tablename__ = "question_reports"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    question_id: Mapped[str] = mapped_column(
        String(180), ForeignKey("questions.id", ondelete="CASCADE"), nullable=False, index=True
    )
    reason: Mapped[str] = mapped_column(String(32), nullable=False)
    details: Mapped[str | None] = mapped_column(String(500))
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="open")
    created_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    reviewed_by: Mapped[int | None] = mapped_column(Integer, ForeignKey("users.id"))
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
