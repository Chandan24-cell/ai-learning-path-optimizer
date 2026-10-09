"""Data-backed subject progress, quiz grading, and recommendation helpers."""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence

from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.models_db import (
    Enrollment,
    Interaction,
    LearnerProfile,
    Question,
    Resource,
    StudentState,
    Subject,
    Topic,
    TopicPrerequisite,
)
from app.profile_options import initial_level
from app.services.recommender import recommend_for
from src.domain import zpd_factor


def get_subject_or_404(db: Session, subject_id: str) -> Subject:
    subject = db.get(Subject, subject_id)
    if subject is None:
        raise HTTPException(status_code=404, detail="Subject not found")
    return subject


def require_enrollment(db: Session, user_id: int, subject_id: str) -> Enrollment:
    enrollment = db.get(Enrollment, (user_id, subject_id))
    if enrollment is None:
        raise HTTPException(status_code=403, detail="Enroll in this subject first")
    return enrollment


def get_topics(db: Session, subject_id: str) -> list[Topic]:
    return db.query(Topic).filter_by(subject_id=subject_id).order_by(Topic.order, Topic.id).all()


def get_state(db: Session, user_id: int, subject_id: str) -> StudentState:
    state = db.get(StudentState, (user_id, subject_id))
    if state is None:
        topic_ids = [topic.id for topic in get_topics(db, subject_id)]
        learner_profile = db.get(LearnerProfile, user_id)
        level, label = (
            initial_level(learner_profile.education_level)
            if learner_profile is not None
            else (25.0, "middle_school")
        )
        state = StudentState(
            user_id=user_id,
            subject_id=subject_id,
            learner_level=level,
            learner_level_label=label,
            learning_goal=learner_profile.learning_goal if learner_profile else "skill",
            mastery_est_json=json.dumps({topic_id: 0.25 for topic_id in topic_ids}),
            attempts_json=json.dumps({topic_id: 0 for topic_id in topic_ids}),
        )
        db.add(state)
        db.flush()
    return state


def get_profile(
    db: Session,
    user_id: int,
    subject_id: str,
    topics: Sequence[Topic] | None = None,
) -> dict:
    state = get_state(db, user_id, subject_id)
    topics = list(topics) if topics is not None else get_topics(db, subject_id)
    mastery = state.mastery_est
    attempts = state.attempts
    for topic in topics:
        mastery.setdefault(topic.id, 0.25)
        attempts.setdefault(topic.id, 0)
    return {
        "ability": float(state.ability or 0.0),
        "motivation": float(state.motivation or 0.6),
        "learner_level": float(state.learner_level),
        "learner_level_label": state.learner_level_label,
        "learning_goal": state.learning_goal,
        "mastery_est": mastery,
        "attempts": attempts,
        "recent_scores": state.recent_scores,
        "total_time_min": float(state.total_time_min or 0.0),
        "engagement_ma": float(state.engagement_ma or 0.5),
        "last_difficulty": float(state.last_difficulty or 3.0),
        "last_score": float(state.last_score or 50.0),
        "n_interactions": int(state.n_interactions or 0),
    }


def get_prerequisites(
    db: Session,
    subject_id: str,
    topic_ids: Sequence[str] | None = None,
) -> dict[str, list[str]]:
    topic_ids = (
        list(topic_ids)
        if topic_ids is not None
        else [topic.id for topic in get_topics(db, subject_id)]
    )
    if not topic_ids:
        return {}
    rows = db.query(TopicPrerequisite).filter(TopicPrerequisite.topic_id.in_(topic_ids)).all()
    result: dict[str, list[str]] = {topic_id: [] for topic_id in topic_ids}
    for row in rows:
        result[row.topic_id].append(row.prerequisite_topic_id)
    return result


def get_catalog(db: Session, subject_id: str) -> list[dict]:
    rows = (
        db.query(Resource, Topic)
        .join(Topic, Resource.topic_id == Topic.id)
        .filter(Topic.subject_id == subject_id)
        .order_by(Topic.order, Resource.id)
        .all()
    )
    return [
        {
            "id": resource.id,
            "topic_id": topic.id,
            "topic_name": topic.name,
            "rtype": resource.type,
            "title": resource.title,
            "difficulty": float(resource.difficulty),
            "duration": float(resource.duration),
            "url": resource.url,
            "body": resource.body,
        }
        for resource, topic in rows
    ]


def get_quiz_questions(db: Session, resource: Resource, limit: int = 3) -> list[Question]:
    return (
        db.query(Question)
        .filter_by(topic_id=resource.topic_id)
        .order_by(
            Question.diagnostic.desc(),
            Question.difficulty,
            Question.id,
        )
        .all()
        if limit <= 0
        else sorted(
            db.query(Question).filter_by(topic_id=resource.topic_id).all(),
            key=lambda question: (
                abs(float(question.difficulty) - float(resource.difficulty)),
                question.id,
            ),
        )[:limit]
    )


def public_question(question: Question) -> dict:
    return {
        "id": question.id,
        "question": question.text,
        "options": question.options,
        "difficulty": float(question.difficulty),
    }


def grade_question_ids(questions: Sequence[Question], answers: Sequence[int]) -> dict:
    if len(questions) != len(answers):
        raise HTTPException(status_code=422, detail="Answer count does not match the quiz")
    if any(
        answer < 0 or answer >= len(question.options)
        for question, answer in zip(questions, answers, strict=True)
    ):
        raise HTTPException(status_code=422, detail="Answer option is outside the question choices")
    correct = sum(
        int(answer == question.correct_option)
        for question, answer in zip(questions, answers, strict=True)
    )
    return {
        "score": round(100.0 * correct / len(questions), 2) if questions else 0.0,
        "correct_answers": correct,
        "question_count": len(questions),
        "feedback": [
            {
                "question_id": question.id,
                "correct": answer == question.correct_option,
                "explanation": question.explanation,
            }
            for question, answer in zip(questions, answers, strict=True)
        ],
    }


def apply_resource_interaction(
    profile: dict,
    resource: Mapping,
    score: float,
    actual_duration: float,
) -> dict:
    topic_id = str(resource["topic_id"])
    mastery = profile["mastery_est"]
    attempts = profile["attempts"]
    old_mastery = float(mastery.get(topic_id, 0.25))
    zpd = zpd_factor(old_mastery, float(resource["difficulty"]))
    new_mastery = min(
        1.0,
        max(0.0, 0.6 * old_mastery + 0.4 * score / 100.0 + 0.03 * zpd * (1.0 - old_mastery)),
    )
    gain = new_mastery - old_mastery
    expected = max(float(resource["duration"]), 1e-6)
    engagement = min(
        1.0,
        max(0.0, 0.6 * zpd + 0.4 * min(max(actual_duration / expected, 0.0), 2.0) / 2.0),
    )
    mastery[topic_id] = new_mastery
    attempts[topic_id] = int(attempts.get(topic_id, 0)) + 1
    scores = list(profile.get("recent_scores", []))
    scores.append(float(score))
    profile["recent_scores"] = scores[-5:]
    profile["total_time_min"] = float(profile.get("total_time_min", 0.0)) + actual_duration
    profile["engagement_ma"] = 0.7 * float(profile.get("engagement_ma", 0.5)) + 0.3 * engagement
    profile["last_difficulty"] = float(resource["difficulty"])
    profile["last_score"] = float(score)
    profile["n_interactions"] = int(profile.get("n_interactions", 0)) + 1
    if len(profile["recent_scores"]) >= 3:
        profile["ability"] = (
            sum(profile["recent_scores"]) / len(profile["recent_scores"]) - 50
        ) / 25
    return {
        "gain": round(gain, 4),
        "new_mastery": round(new_mastery, 4),
        "engagement": round(engagement, 4),
        "difficulty_fit": round(zpd, 4),
    }


def save_profile(state: StudentState, profile: Mapping) -> None:
    state.mastery_est_json = json.dumps(profile["mastery_est"])
    state.attempts_json = json.dumps(profile["attempts"])
    state.recent_scores_json = json.dumps(profile["recent_scores"])
    state.total_time_min = float(profile["total_time_min"])
    state.engagement_ma = float(profile["engagement_ma"])
    state.last_difficulty = float(profile["last_difficulty"])
    state.last_score = float(profile["last_score"])
    state.n_interactions = int(profile["n_interactions"])
    state.ability = float(profile["ability"])
    if "learner_level" in profile:
        state.learner_level = float(profile["learner_level"])
        state.learner_level_label = str(profile["learner_level_label"])


def recommend_subject(
    db: Session,
    user_id: int,
    subject_id: str,
    top_k: int = 5,
) -> list[dict]:
    topics = get_topics(db, subject_id)
    profile = get_profile(db, user_id, subject_id, topics=topics)
    catalog = get_catalog(db, subject_id)
    prerequisites = get_prerequisites(db, subject_id, topic_ids=[topic.id for topic in topics])
    limited_topics = {topic.id for topic in topics if topic.quiz_status == "limited"}
    if limited_topics:
        prerequisites = {
            topic_id: [
                prerequisite_id
                for prerequisite_id in prerequisite_ids
                if prerequisite_id not in limited_topics
            ]
            for topic_id, prerequisite_ids in prerequisites.items()
        }
    recent_interactions = (
        db.query(Interaction.resource_id, Interaction.topic)
        .filter_by(user_id=user_id, subject_id=subject_id)
        .order_by(Interaction.id.desc())
        .limit(12)
        .all()
    )
    recent_history = [
        {"resource_id": resource_id, "topic_id": topic_id}
        for resource_id, topic_id in recent_interactions
    ]
    return recommend_for(
        profile, catalog, prerequisites, top_k=top_k, recent_history=recent_history
    )
