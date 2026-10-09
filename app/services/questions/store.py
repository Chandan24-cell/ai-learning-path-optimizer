"""Persistence helpers for lazily generated, source-grounded question banks."""

from __future__ import annotations

import hashlib
import json

from sqlalchemy.orm import Session

from app.models_db import Question, Subject, Topic
from app.services.questions.rule_based import (
    LIMITED_QUIZ_THRESHOLD,
    RuleBasedQuestionGenerator,
)


def ensure_topic_question_bank(db: Session, topic: Topic, learner_level: float) -> list[Question]:
    query = db.query(Question).filter(
        Question.topic_id == topic.id,
        Question.source_url.is_not(None),
        Question.generator_version.is_not(None),
    )
    existing = query.order_by(Question.id).all()
    if existing:
        return existing
    subject = db.get(Subject, topic.subject_id)
    if subject is None or not topic.source_extract or not topic.source_url:
        topic.quiz_status = "limited"
        return []
    if topic.quiz_status != "not_generated":
        return []

    topics = (
        db.query(Topic).filter_by(subject_id=topic.subject_id).order_by(Topic.order, Topic.id).all()
    )
    provenance = _provenance(topic.provenance)
    sibling_facts: list[dict[str, str]] = []
    sibling_terms: list[str] = []
    for sibling in topics:
        sibling_provenance = _provenance(sibling.provenance)
        sibling_facts.extend(_facts(sibling_provenance))
        sibling_terms.extend(_strings(sibling_provenance.get("linked_terms")))

    generated = RuleBasedQuestionGenerator().generate_questions(
        subject.name,
        topic.name,
        source_extract=topic.source_extract,
        source_url=topic.source_url,
        linked_terms=_strings(provenance.get("linked_terms")),
        sibling_topics=[item.name for item in topics],
        sibling_terms=sibling_terms,
        wikidata_facts=_facts(provenance),
        sibling_facts=sibling_facts,
        topic_order=topic.order,
        topic_count=len(topics),
        learner_level=learner_level,
    )
    for item in generated:
        digest = hashlib.sha256(
            f"{topic.id}|{item['question_type']}|{item['text']}".encode()
        ).hexdigest()[:14]
        question_id = f"{topic.id}.rb.{digest}"[:180]
        if db.get(Question, question_id) is not None:
            continue
        db.add(
            Question(
                id=question_id,
                topic_id=topic.id,
                difficulty=item["difficulty"],
                text=item["text"],
                options_json=json.dumps(item["options"], ensure_ascii=True),
                correct_option=item["correct_option"],
                explanation=item["explanation"],
                diagnostic=False,
                question_type=item["question_type"],
                source_sentence=item["source_sentence"],
                source_url=item["source_url"],
                attribution=item["attribution"],
                generated_at=item["generated_at"],
                generator_version=item["generator_version"],
                status=item["status"],
            )
        )
    db.flush()
    count_query = db.query(Question.id).filter(
        Question.topic_id == topic.id,
        Question.source_url.is_not(None),
        Question.generator_version.is_not(None),
    )
    count = count_query.count()
    topic.quiz_status = "ready" if count >= LIMITED_QUIZ_THRESHOLD else "limited"
    return query.order_by(Question.id).all()


def _provenance(value: str | None) -> dict:
    if not value:
        return {}
    try:
        parsed = json.loads(value)
    except TypeError, ValueError:
        return {}
    return parsed if isinstance(parsed, dict) else {}


def _strings(value: object) -> list[str]:
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, str)]


def _facts(provenance: dict) -> list[dict[str, str]]:
    value = provenance.get("wikidata_facts")
    if not isinstance(value, list):
        return []
    return [
        {
            key: item[key]
            for key in ("property", "value", "value_type")
            if isinstance(item.get(key), str)
        }
        for item in value
        if isinstance(item, dict)
    ]
