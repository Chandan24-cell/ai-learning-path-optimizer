"""Shared enrollment limit and activation helpers."""

from __future__ import annotations

from threading import Lock

from fastapi import HTTPException
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models_db import Enrollment, LearnerProfile, Subject, Topic, User
from app.services.discovery.service import depth_for_level
from app.services.subject_learning import get_state

MAX_ACTIVE_ENROLLMENTS = 8
_enrollment_lock = Lock()


def ensure_enrollment_capacity(db: Session, user_id: int, subject_id: str) -> None:
    """Reject a new enrollment before creating or importing subject content."""
    if db.get(Enrollment, (user_id, subject_id)) is not None:
        return
    count = db.query(func.count(Enrollment.user_id)).filter(Enrollment.user_id == user_id).scalar()
    if count >= MAX_ACTIVE_ENROLLMENTS:
        raise HTTPException(
            status_code=409,
            detail="You can enroll in up to 8 subjects. Unenroll from one to free a slot.",
        )


def enroll_user(
    db: Session,
    user: User,
    subject: Subject,
    target_depth: str | None = None,
) -> Enrollment:
    """Enroll and activate a subject while enforcing the per-user cap."""
    with _enrollment_lock:
        enrollment = db.get(Enrollment, (user.id, subject.id))
        if enrollment is None:
            ensure_enrollment_capacity(db, user.id, subject.id)
            profile = db.get(LearnerProfile, user.id)
            has_topics = db.query(Topic.id).filter_by(subject_id=subject.id).first() is not None
            enrollment = Enrollment(
                user_id=user.id,
                subject_id=subject.id,
                diagnostic_completed=not has_topics,
                education_level_used=profile.education_level if profile else None,
                target_depth=target_depth
                or depth_for_level(profile.education_level if profile else "middle_school"),
            )
            db.add(enrollment)
            db.flush()
            get_state(db, user.id, subject.id)
        elif target_depth:
            enrollment.target_depth = target_depth
        user.active_subject_id = subject.id
        db.commit()
    return enrollment
