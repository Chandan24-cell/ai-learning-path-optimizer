"""Learner onboarding, profile management, and profile-choice endpoints."""

from __future__ import annotations

from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.database import get_db
from app.dependencies import current_user
from app.models_db import LearnerProfile, StudentState, User
from app.profile_options import initial_level, load_profile_options
from app.schemas import LearnerProfileIn

router = APIRouter(prefix="/api", tags=["learner profile"])


def _profile_values(profile: LearnerProfile) -> dict:
    return {
        "country": profile.country,
        "language": profile.language,
        "education_level": profile.education_level,
        "institution_type": profile.institution_type,
        "grade_year": profile.grade_year,
        "curriculum_program": profile.curriculum_program,
        "field_of_study": profile.field_of_study,
        "learning_goal": profile.learning_goal,
        "weekly_time_hours": profile.weekly_time_hours,
        "learning_style": profile.learning_style,
        "prior_experience": profile.prior_experience,
        "consent_version": profile.consent_version,
        "consent_at": profile.consent_at.isoformat(),
        "updated_at": profile.updated_at.isoformat() if profile.updated_at else None,
    }


def _validate_choices(payload: LearnerProfileIn, options: dict) -> None:
    countries = {item["id"]: item for item in options["countries"]}
    if payload.country not in countries:
        raise HTTPException(status_code=422, detail="Choose a country from the onboarding options")
    if payload.language not in options["languages"]:
        raise HTTPException(status_code=422, detail="Choose a language from the onboarding options")

    for field, collection in (
        ("education_level", "education_levels"),
        ("institution_type", "institution_types"),
        ("learning_goal", "learning_goals"),
        ("learning_style", "learning_styles"),
        ("prior_experience", "prior_experience_options"),
    ):
        allowed = {item["id"] for item in options[collection]}
        if getattr(payload, field) not in allowed:
            raise HTTPException(
                status_code=422,
                detail=f"Choose a valid {field.replace('_', ' ')} from the onboarding options",
            )

    if (
        payload.curriculum_program
        and payload.curriculum_program not in countries[payload.country]["curricula"]
    ):
        raise HTTPException(
            status_code=422,
            detail="Choose a curriculum or program offered for the selected country",
        )


@router.get("/onboarding/options")
def onboarding_options() -> dict:
    return load_profile_options()


@router.get("/me/profile")
def get_my_profile(user: User = Depends(current_user), db: Session = Depends(get_db)) -> dict:
    if user.role != "student":
        return {"required": False, "completed": True, "profile": None}
    profile = db.get(LearnerProfile, user.id)
    return {
        "required": True,
        "completed": profile is not None,
        "profile": _profile_values(profile) if profile else None,
    }


@router.put("/me/profile")
def save_my_profile(
    payload: LearnerProfileIn,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
) -> dict:
    if user.role != "student":
        raise HTTPException(status_code=403, detail="Only student accounts have learner profiles")
    options = load_profile_options()
    _validate_choices(payload, options)
    profile = db.get(LearnerProfile, user.id)
    now = datetime.now(UTC)
    values = payload.model_dump(exclude={"consent"})
    education_level_changed = profile is None or profile.education_level != payload.education_level
    if profile is None:
        profile = LearnerProfile(user_id=user.id, consent_at=now, **values)
        db.add(profile)
    else:
        for key, value in values.items():
            setattr(profile, key, value)
        profile.consent_at = now
    profile.consent_version = options["consent_version"]
    level, label = initial_level(payload.education_level)
    states = db.query(StudentState).filter_by(user_id=user.id).all()
    for state in states:
        if education_level_changed:
            state.learner_level = level
            state.learner_level_label = label
        state.learning_goal = payload.learning_goal
    db.commit()
    db.refresh(profile)
    return {"required": True, "completed": True, "profile": _profile_values(profile)}


@router.delete("/me/profile")
def delete_my_profile(user: User = Depends(current_user), db: Session = Depends(get_db)) -> dict:
    if user.role != "student":
        raise HTTPException(status_code=403, detail="Only student accounts have learner profiles")
    profile = db.get(LearnerProfile, user.id)
    if profile is not None:
        db.delete(profile)
    for state in db.query(StudentState).filter_by(user_id=user.id).all():
        state.learner_level = 25.0
        state.learner_level_label = "middle_school"
        state.learning_goal = "skill"
    db.commit()
    return {"status": "profile deleted", "onboarding_required": True}
