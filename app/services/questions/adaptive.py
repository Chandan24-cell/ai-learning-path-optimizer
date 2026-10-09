"""Per-learner question selection and exposure tracking."""

from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy.orm import Session

from app.models_db import Question, QuestionExposure, QuestionSession, Topic
from app.services.questions.rule_based import adaptive_difficulty


@dataclass(frozen=True)
class SelectedQuestion:
    question: Question
    difficulty: float
    reused: bool


def select_question(
    db: Session,
    *,
    user_id: int,
    subject_id: str,
    session: QuestionSession,
    topic: Topic,
    questions: list[Question],
    learner_level: float,
    mastery: float,
    previous_correct: bool | None,
    topic_count: int,
    prefer_diagnostic: bool = False,
) -> SelectedQuestion | None:
    if not questions:
        return None

    ids = [question.id for question in questions]
    already_in_session = {
        question_id
        for (question_id,) in (
            db.query(QuestionExposure.question_id)
            .filter(
                QuestionExposure.session_id == session.id,
                QuestionExposure.question_id.in_(ids),
            )
            .all()
        )
    }
    candidates = [question for question in questions if question.id not in already_in_session]
    if not candidates:
        return None

    previously_seen = {
        question_id
        for (question_id,) in (
            db.query(QuestionExposure.question_id)
            .filter(
                QuestionExposure.user_id == user_id,
                QuestionExposure.subject_id == subject_id,
                QuestionExposure.question_id.in_([question.id for question in candidates]),
            )
            .distinct()
            .all()
        )
    }
    unseen = [question for question in candidates if question.id not in previously_seen]
    reused = not unseen
    pool = unseen if unseen else candidates
    desired_difficulty = max(
        1.0,
        min(
            5.0,
            1.0
            + 4.0 * mastery
            + (0.5 if previous_correct is True else -0.5 if previous_correct is False else 0.0),
        ),
    )
    ranked = [
        (
            question,
            adaptive_difficulty(
                float(question.difficulty),
                topic.order,
                topic_count,
                learner_level,
                mastery,
                previous_correct,
            ),
        )
        for question in pool
    ]
    question, difficulty = min(
        ranked,
        key=lambda item: (
            not item[0].diagnostic if prefer_diagnostic else False,
            abs(item[1] - desired_difficulty),
            item[0].id,
        ),
    )
    db.add(
        QuestionExposure(
            user_id=user_id,
            subject_id=subject_id,
            topic_id=topic.id,
            question_id=question.id,
            session_id=session.id,
        )
    )
    if reused:
        session.reused_questions = True
    return SelectedQuestion(question=question, difficulty=difficulty, reused=reused)


def public_adaptive_question(selected: SelectedQuestion) -> dict:
    question = selected.question
    return {
        "id": question.id,
        "question": question.text,
        "options": question.options,
        "question_type": question.question_type,
        "difficulty": selected.difficulty,
        "status": question.status,
        "attribution": question.attribution,
        "source_url": question.source_url,
    }
