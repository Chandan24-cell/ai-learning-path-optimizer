"""Content-pack schema validation and transactional, idempotent import."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator
from sqlalchemy.orm import Session

from app.models_db import Question, Resource, Subject, Topic, TopicPrerequisite

_SLUG = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")


class ResourcePack(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str = Field(min_length=1, max_length=100)
    type: Literal["video", "article", "quiz", "interactive", "project"]
    title: str = Field(min_length=1, max_length=200)
    difficulty: float = Field(ge=1, le=5)
    duration: float = Field(gt=0, le=600)
    url: str | None = None
    body: str | None = None

    @model_validator(mode="after")
    def require_content(self) -> ResourcePack:
        if not (self.url or self.body):
            raise ValueError("a resource needs a non-empty url or body")
        return self


class QuestionPack(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str = Field(min_length=1, max_length=100)
    difficulty: float = Field(ge=1, le=5)
    text: str = Field(min_length=1, max_length=2000)
    options: list[str] = Field(min_length=2, max_length=8)
    correct_option: int = Field(ge=0)
    explanation: str = Field(min_length=1, max_length=2000)
    diagnostic: bool = False

    @model_validator(mode="after")
    def validate_answer(self) -> QuestionPack:
        if self.correct_option >= len(self.options):
            raise ValueError("correct_option must point to one of the options")
        if any(not option.strip() for option in self.options):
            raise ValueError("question options cannot be empty")
        return self


class TopicPack(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str = Field(min_length=1, max_length=80)
    name: str = Field(min_length=1, max_length=160)
    order: int = Field(ge=1)
    prerequisites: list[str] = Field(default_factory=list)
    resources: list[ResourcePack] = Field(min_length=1)
    questions: list[QuestionPack] = Field(min_length=8)

    @model_validator(mode="after")
    def validate_question_levels(self) -> TopicPack:
        levels = {int(question.difficulty) for question in self.questions}
        if len(levels) < 3 or min(levels) > 2 or max(levels) < 4:
            raise ValueError("each topic needs questions at easy, mixed, and harder levels")
        if sum(question.diagnostic for question in self.questions) != 1:
            raise ValueError("each topic needs exactly one diagnostic question")
        if len({question.id for question in self.questions}) != len(self.questions):
            raise ValueError("question ids must be unique within a topic")
        if len({resource.id for resource in self.resources}) != len(self.resources):
            raise ValueError("resource ids must be unique within a topic")
        return self


class ContentPack(BaseModel):
    model_config = ConfigDict(extra="forbid")

    slug: str = Field(min_length=1, max_length=80)
    name: str = Field(min_length=1, max_length=120)
    description: str = Field(default="", max_length=2000)
    questions_status: str = Field(min_length=1, max_length=80)
    topics: list[TopicPack] = Field(min_length=5)

    @model_validator(mode="after")
    def validate_graph_and_ids(self) -> ContentPack:
        if not _SLUG.fullmatch(self.slug):
            raise ValueError("subject slug must contain lowercase letters, numbers, and hyphens")
        ids = [topic.id for topic in self.topics]
        if len(ids) != len(set(ids)):
            raise ValueError("topic ids must be unique within a subject")
        if len({topic.order for topic in self.topics}) != len(self.topics):
            raise ValueError("topic order values must be unique")
        topic_ids = set(ids)
        for topic in self.topics:
            if not _SLUG.fullmatch(topic.id):
                raise ValueError(f"invalid topic id: {topic.id}")
            if len(self.slug) + len(topic.id) + 1 > 160:
                raise ValueError(f"topic id is too long after subject prefix: {topic.id}")
            missing = set(topic.prerequisites) - topic_ids
            if missing:
                raise ValueError(f"topic {topic.id} has unknown prerequisites: {sorted(missing)}")
            if topic.id in topic.prerequisites:
                raise ValueError(f"topic {topic.id} cannot require itself")
            for item_id in (
                *(resource.id for resource in topic.resources),
                *(question.id for question in topic.questions),
            ):
                if not _SLUG.fullmatch(item_id):
                    raise ValueError(f"invalid content id: {item_id}")
                if len(self.slug) + len(topic.id) + len(item_id) + 2 > 180:
                    raise ValueError(f"content id is too long after subject prefix: {item_id}")
        visiting: set[str] = set()
        visited: set[str] = set()
        by_id = {topic.id: topic for topic in self.topics}

        def visit(topic_id: str) -> None:
            if topic_id in visiting:
                raise ValueError("topic prerequisites must not contain a cycle")
            if topic_id in visited:
                return
            visiting.add(topic_id)
            for prerequisite_id in by_id[topic_id].prerequisites:
                visit(prerequisite_id)
            visiting.remove(topic_id)
            visited.add(topic_id)

        for topic_id in ids:
            visit(topic_id)
        if "draft" not in self.questions_status.casefold() or "review" not in (
            self.questions_status.casefold()
        ):
            raise ValueError("question status must state that questions are draft and need review")
        return self


def load_content_pack(path: str | Path) -> ContentPack:
    """Load and validate a directory containing content.json or a JSON file."""
    target = Path(path)
    if target.is_dir():
        target = target / "content.json"
    if not target.is_file():
        raise FileNotFoundError(f"content pack not found: {target}")
    try:
        return ContentPack.model_validate_json(target.read_text(encoding="utf-8"))
    except (ValueError, UnicodeDecodeError) as exc:
        raise ValueError(f"invalid content pack {target}: {exc}") from exc


def import_content_pack(path: str | Path, db: Session) -> dict[str, int | str]:
    """Validate then upsert a content pack in one database transaction."""
    pack = load_content_pack(path)
    db.merge(
        Subject(
            id=pack.slug,
            name=pack.name,
            description=pack.description,
            questions_status=pack.questions_status,
            source="pack",
            status="draft",
            created_by=None,
        )
    )
    topic_ids = {item.id: f"{pack.slug}.{item.id}" for item in pack.topics}

    for item in sorted(pack.topics, key=lambda topic: topic.order):
        topic_id = topic_ids[item.id]
        db.merge(
            Topic(
                id=topic_id,
                subject_id=pack.slug,
                slug=item.id,
                name=item.name,
                order=item.order,
            )
        )

    db.flush()
    for item in pack.topics:
        topic_id = topic_ids[item.id]
        db.query(TopicPrerequisite).filter_by(topic_id=topic_id).delete(synchronize_session=False)
        for prerequisite in item.prerequisites:
            db.merge(
                TopicPrerequisite(
                    topic_id=topic_id,
                    prerequisite_topic_id=topic_ids[prerequisite],
                )
            )
        resource_ids = {f"{pack.slug}.{item.id}.{resource.id}" for resource in item.resources}
        question_ids = {f"{pack.slug}.{item.id}.{question.id}" for question in item.questions}
        db.query(Resource).filter(
            Resource.topic_id == topic_id, ~Resource.id.in_(resource_ids)
        ).delete(synchronize_session=False)
        db.query(Question).filter(
            Question.topic_id == topic_id, ~Question.id.in_(question_ids)
        ).delete(synchronize_session=False)
        for resource in item.resources:
            db.merge(
                Resource(
                    id=f"{pack.slug}.{item.id}.{resource.id}",
                    topic_id=topic_id,
                    type=resource.type,
                    title=resource.title,
                    difficulty=resource.difficulty,
                    duration=resource.duration,
                    url=resource.url,
                    body=resource.body,
                )
            )
        for question in item.questions:
            db.merge(
                Question(
                    id=f"{pack.slug}.{item.id}.{question.id}",
                    topic_id=topic_id,
                    difficulty=question.difficulty,
                    text=question.text,
                    options_json=json.dumps(question.options, ensure_ascii=False),
                    correct_option=question.correct_option,
                    explanation=question.explanation,
                    diagnostic=question.diagnostic,
                )
            )
    db.commit()
    return {
        "subject": pack.slug,
        "topics": len(pack.topics),
        "resources": sum(len(topic.resources) for topic in pack.topics),
        "questions": sum(len(topic.questions) for topic in pack.topics),
    }
