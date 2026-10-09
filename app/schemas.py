"""Pydantic request/response models."""

from __future__ import annotations

import re
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.security import MAX_PASSWORD_BYTES

COMMON_PASSWORDS = {"password123", "1234567890", "qwerty1234", "letmein123", "admin12345"}


def _normalize_username(value: str) -> str:
    normalized = value.strip().lower()
    if not re.fullmatch(r"[a-z0-9_]{3,32}", normalized):
        raise ValueError("Username must be 3-32 letters, numbers, or underscores")
    return normalized


class RegisterIn(BaseModel):
    username: str
    password: str
    role: Literal["student", "teacher"] = "student"

    @field_validator("username")
    @classmethod
    def normalize_username(cls, value: str) -> str:
        return _normalize_username(value)

    @field_validator("password")
    @classmethod
    def validate_password_length(cls, value: str) -> str:
        if len(value) < 10:
            raise ValueError("Password must be at least 10 characters")
        if value.isdigit():
            raise ValueError("Password cannot contain only digits")
        if value.casefold() in COMMON_PASSWORDS:
            raise ValueError("Choose a less common password")
        if len(value.encode("utf-8")) > MAX_PASSWORD_BYTES:
            raise ValueError("Password must be no more than 72 UTF-8 bytes")
        return value


class LoginIn(BaseModel):
    username: str
    password: str

    @field_validator("username")
    @classmethod
    def normalize_username(cls, value: str) -> str:
        return _normalize_username(value)


class RefreshIn(BaseModel):
    refresh_token: str


class TokenOut(BaseModel):
    token: str
    refresh_token: str
    username: str
    role: Literal["student", "teacher"]


class LogoutIn(BaseModel):
    refresh_token: str


class DeleteAccountIn(BaseModel):
    password: str


class LearnerProfileIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    country: str = Field(min_length=2, max_length=120)
    language: str = Field(min_length=2, max_length=80)
    education_level: str = Field(min_length=1, max_length=40)
    institution_type: str = Field(min_length=1, max_length=40)
    grade_year: str = Field(min_length=1, max_length=80)
    curriculum_program: str | None = Field(default=None, max_length=120)
    field_of_study: str = Field(min_length=1, max_length=120)
    learning_goal: str = Field(min_length=1, max_length=24)
    weekly_time_hours: float = Field(ge=0.5, le=80)
    learning_style: str = Field(min_length=1, max_length=24)
    prior_experience: str = Field(min_length=1, max_length=24)
    consent: bool

    @field_validator(
        "country",
        "language",
        "education_level",
        "institution_type",
        "grade_year",
        "curriculum_program",
        "field_of_study",
        "learning_goal",
        "learning_style",
        "prior_experience",
    )
    @classmethod
    def strip_profile_text(cls, value: str | None) -> str | None:
        return value.strip() if value is not None else None

    @model_validator(mode="after")
    def validate_required_text_and_consent(self) -> LearnerProfileIn:
        required_text = (
            self.country,
            self.language,
            self.education_level,
            self.institution_type,
            self.grade_year,
            self.field_of_study,
            self.learning_goal,
            self.learning_style,
            self.prior_experience,
        )
        if any(not value for value in required_text):
            raise ValueError("Required profile fields cannot be blank")
        if not self.consent:
            raise ValueError("Consent is required to save a learner profile")
        return self


class InteractionIn(BaseModel):
    action: int
    answers: list[int] = Field(min_length=1, max_length=10)
    duration: float = Field(
        ge=0.5,
        le=120.0,
        description="Time spent on the activity, in minutes (0.5 to 120).",
    )


class SubjectSwitchIn(BaseModel):
    subject_id: str = Field(min_length=1, max_length=80)


class SubjectManualIn(BaseModel):
    name: str = Field(min_length=2, max_length=120)

    @field_validator("name")
    @classmethod
    def strip_subject_name(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("Subject name cannot be blank")
        return value


class DiscoveredSubjectIn(BaseModel):
    name: str = Field(min_length=2, max_length=120)
    source_url: str = Field(min_length=1, max_length=2000)
    target_depth: Literal["beginner", "intermediate", "advanced"] | None = None
    manual_subject_id: str | None = Field(default=None, min_length=1, max_length=80)


class EnrollmentIn(BaseModel):
    target_depth: Literal["beginner", "intermediate", "advanced"] | None = None


class ReferenceBookIn(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    authors: list[str] = Field(default_factory=list, max_length=5)
    edition: str | None = Field(default=None, max_length=80)
    publisher: str | None = Field(default=None, max_length=120)
    year: int | None = Field(default=None, ge=1400, le=2100)
    isbn: list[str] = Field(default_factory=list, max_length=5)
    link: str = Field(min_length=1, max_length=2000)


class DiagnosticSubmitIn(BaseModel):
    answers: dict[str, int] = Field(default_factory=dict, max_length=100)
    self_ratings: dict[str, int] = Field(default_factory=dict, max_length=100)
    session_id: str | None = Field(default=None, max_length=80)

    @field_validator("self_ratings")
    @classmethod
    def validate_self_ratings(cls, value: dict[str, int]) -> dict[str, int]:
        if any(rating < 0 or rating > 5 for rating in value.values()):
            raise ValueError("Self-ratings must be between 0 and 5")
        return value


class TopicRatingIn(BaseModel):
    rating: int = Field(ge=0, le=5)


class ResourceSubmitIn(BaseModel):
    answers: list[int] = Field(min_length=1, max_length=10)
    duration: float = Field(ge=0.5, le=120.0)


class AdaptiveQuestionAnswerIn(BaseModel):
    question_id: str = Field(min_length=1, max_length=180)
    answer: int = Field(ge=0, le=7)
    duration: float = Field(ge=0.1, le=120.0)


class QuestionReportIn(BaseModel):
    reason: Literal["incorrect", "ambiguous", "source", "other"]
    details: str | None = Field(default=None, max_length=500)


class QuestionReportReviewIn(BaseModel):
    status: Literal["reviewed", "dismissed"]


class TopicCreateIn(BaseModel):
    slug: str = Field(pattern=r"^[a-z0-9]+(?:-[a-z0-9]+)*$", max_length=80)
    name: str = Field(min_length=1, max_length=160)
    order: int = Field(ge=1)
    prerequisites: list[str] = Field(default_factory=list)


class TopicUpdateIn(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=160)
    order: int | None = Field(default=None, ge=1)
    prerequisites: list[str] | None = None


class ResourceCreateIn(BaseModel):
    id: str = Field(pattern=r"^[a-z0-9]+(?:-[a-z0-9]+)*$", max_length=100)
    type: Literal["video", "article", "quiz", "interactive", "project"]
    title: str = Field(min_length=1, max_length=200)
    difficulty: float = Field(ge=1, le=5)
    duration: float = Field(gt=0, le=600)
    url: str | None = None
    body: str | None = None

    @model_validator(mode="after")
    def require_content(self) -> ResourceCreateIn:
        if not (self.url or self.body):
            raise ValueError("a resource needs a non-empty url or body")
        return self


class ResourceUpdateIn(BaseModel):
    type: Literal["video", "article", "quiz", "interactive", "project"] | None = None
    title: str | None = Field(default=None, min_length=1, max_length=200)
    difficulty: float | None = Field(default=None, ge=1, le=5)
    duration: float | None = Field(default=None, gt=0, le=600)
    url: str | None = None
    body: str | None = None


class QuestionCreateIn(BaseModel):
    id: str = Field(pattern=r"^[a-z0-9]+(?:-[a-z0-9]+)*$", max_length=100)
    difficulty: float = Field(ge=1, le=5)
    text: str = Field(min_length=1, max_length=2000)
    options: list[str] = Field(min_length=2, max_length=8)
    correct_option: int = Field(ge=0)
    explanation: str = Field(min_length=1, max_length=2000)
    diagnostic: bool = False

    @model_validator(mode="after")
    def validate_answer(self) -> QuestionCreateIn:
        if self.correct_option >= len(self.options):
            raise ValueError("correct_option must point to one of the options")
        if any(not option.strip() for option in self.options):
            raise ValueError("question options cannot be empty")
        return self


class QuestionUpdateIn(BaseModel):
    difficulty: float | None = Field(default=None, ge=1, le=5)
    text: str | None = Field(default=None, min_length=1, max_length=2000)
    options: list[str] | None = Field(default=None, min_length=2, max_length=8)
    correct_option: int | None = Field(default=None, ge=0)
    explanation: str | None = Field(default=None, min_length=1, max_length=2000)
    diagnostic: bool | None = None
    status: Literal["approved"] | None = None
