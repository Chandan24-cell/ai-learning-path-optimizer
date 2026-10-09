"""Legacy active-subject API plus catalog and learner history."""

from __future__ import annotations

from typing import cast

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.database import get_db
from app.dependencies import completed_profile_user
from app.models_db import Enrollment, Interaction, Resource, StudentState, Subject, Topic, User
from app.schemas import InteractionIn
from app.services.recommender import get_mode
from app.services.subject_learning import (
    apply_resource_interaction,
    get_profile,
    get_quiz_questions,
    get_state,
    get_topics,
    grade_question_ids,
    public_question,
    recommend_subject,
    save_profile,
)
from app.services.subject_learning import (
    get_catalog as subject_catalog,
)

router = APIRouter(prefix="/api", tags=["learning"])


def _active_subject(user: User, db: Session) -> str:
    subject_id = user.active_subject_id
    if subject_id is None:
        raise HTTPException(status_code=409, detail="Choose a subject before opening learning")
    if db.get(Subject, subject_id) is None:
        raise HTTPException(status_code=409, detail="Import a subject content pack first")
    enrollment = db.get(Enrollment, (user.id, subject_id))
    if enrollment is None:
        enrollment = Enrollment(user_id=user.id, subject_id=subject_id, diagnostic_completed=True)
        db.add(enrollment)
        db.flush()
    get_state(db, user.id, subject_id)
    return subject_id


def _profile_dict(state: StudentState, topics: list[Topic]) -> dict:
    mastery = state.mastery_est
    attempts = state.attempts
    return {
        "subject_id": state.subject_id,
        "ability": float(state.ability or 0.0),
        "motivation": float(state.motivation or 0.6),
        "learner_level": float(state.learner_level),
        "learner_level_label": state.learner_level_label,
        "learning_goal": state.learning_goal,
        "mastery_est": [float(mastery.get(topic.id, 0.25)) for topic in topics],
        "mastery_by_topic": {topic.id: float(mastery.get(topic.id, 0.25)) for topic in topics},
        "attempts": [int(attempts.get(topic.id, 0)) for topic in topics],
        "recent_scores": state.recent_scores,
        "total_time_min": float(state.total_time_min or 0.0),
        "engagement_ma": float(state.engagement_ma or 0.5),
        "last_difficulty": float(state.last_difficulty or 3.0),
        "last_score": float(state.last_score or 50.0),
        "n_interactions": int(state.n_interactions or 0),
    }


def _legacy_recommendations(db: Session, user_id: int, subject_id: str, top_k: int) -> list[dict]:
    catalog = subject_catalog(db, subject_id)
    action_by_resource = {item["id"]: index for index, item in enumerate(catalog)}
    recommendations = recommend_subject(db, user_id, subject_id, top_k=top_k)
    return [
        {**recommendation, "action": action_by_resource[recommendation["resource_id"]]}
        for recommendation in recommendations
        if recommendation["resource_id"] in action_by_resource
    ]


@router.get("/meta")
def meta():
    return {"recommender_mode": get_mode()}


@router.get("/me/state")
def get_active_state(user: User = Depends(completed_profile_user), db: Session = Depends(get_db)):
    subject_id = _active_subject(user, db)
    state = get_state(db, user.id, subject_id)
    db.commit()
    return _profile_dict(state, get_topics(db, subject_id))


@router.get("/recommend")
def recommend_active_subject(
    top_k: int = Query(default=5, ge=1, le=20),
    user: User = Depends(completed_profile_user),
    db: Session = Depends(get_db),
):
    subject_id = _active_subject(user, db)
    return {
        "subject_id": subject_id,
        "recommendations": _legacy_recommendations(db, user.id, subject_id, top_k),
    }


@router.get("/quiz/{action}")
def legacy_quiz(
    action: int, user: User = Depends(completed_profile_user), db: Session = Depends(get_db)
):
    subject_id = _active_subject(user, db)
    catalog = subject_catalog(db, subject_id)
    if not 0 <= action < len(catalog):
        raise HTTPException(status_code=400, detail="Invalid action index")
    resource = db.get(Resource, catalog[action]["id"])
    questions = get_quiz_questions(db, cast(Resource, resource))
    return {
        "action": action,
        "resource_id": catalog[action]["id"],
        "topic": catalog[action]["topic_name"],
        "questions": [public_question(question) for question in questions],
    }


@router.get("/catalog")
def active_catalog(db: Session = Depends(get_db)):
    catalog = subject_catalog(db, "mathematics") if db.get(Subject, "mathematics") else []
    return {
        "catalog": [
            {
                "action": index,
                "id": item["id"],
                "topic": item["topic_name"],
                "resource_type": item["rtype"],
                "title": item["title"],
                "difficulty": round(float(item["difficulty"]), 2),
                "duration_min": float(item["duration"]),
            }
            for index, item in enumerate(catalog)
        ]
    }


@router.post("/interaction")
def legacy_log_interaction(
    payload: InteractionIn,
    user: User = Depends(completed_profile_user),
    db: Session = Depends(get_db),
):
    subject_id = _active_subject(user, db)
    catalog = subject_catalog(db, subject_id)
    if not 0 <= payload.action < len(catalog):
        raise HTTPException(status_code=400, detail="Invalid action index")
    entry = catalog[payload.action]
    resource = db.get(Resource, entry["id"])
    questions = get_quiz_questions(db, cast(Resource, resource))
    grade = grade_question_ids(questions, payload.answers)
    profile = get_profile(db, user.id, subject_id)
    outcome = apply_resource_interaction(profile, entry, grade["score"], payload.duration)
    outcome.update(grade)
    state = get_state(db, user.id, subject_id)
    save_profile(state, profile)
    db.add(
        Interaction(
            user_id=user.id,
            subject_id=subject_id,
            resource_id=entry["id"],
            action=payload.action,
            topic=entry["topic_id"],
            rtype=entry["rtype"],
            difficulty=entry["difficulty"],
            duration=payload.duration,
            score=grade["score"],
            gain=outcome["gain"],
            engagement=outcome["engagement"],
        )
    )
    db.commit()
    return {
        "outcome": outcome,
        "state": _profile_dict(state, get_topics(db, subject_id)),
        "next_recommendations": _legacy_recommendations(db, user.id, subject_id, 5),
    }


@router.get("/history")
def active_history(
    limit: int = Query(default=20, ge=1, le=200),
    user: User = Depends(completed_profile_user),
    db: Session = Depends(get_db),
):
    subject_id = _active_subject(user, db)
    rows = (
        db.query(Interaction)
        .filter_by(user_id=user.id, subject_id=subject_id)
        .order_by(Interaction.id.desc())
        .limit(limit)
        .all()
    )
    return {
        "history": [
            {
                "id": row.id,
                "topic": row.topic,
                "resource_id": row.resource_id,
                "resource_type": row.rtype,
                "difficulty": round(row.difficulty if row.difficulty is not None else 0.0, 2),
                "duration": round(row.duration if row.duration is not None else 0.0, 1),
                "score": round(row.score if row.score is not None else 0.0, 1),
                "gain": round(float(row.gain or 0.0), 4),
                "engagement": round(float(row.engagement or 0.0), 4),
                "timestamp": row.timestamp.isoformat() if row.timestamp else None,
            }
            for row in rows
        ]
    }
