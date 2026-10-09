"""FastAPI dependency: extract the current authenticated user."""

from __future__ import annotations

from fastapi import Depends, Header, HTTPException
from sqlalchemy.orm import Session

from app.database import get_db
from app.models_db import LearnerProfile, User
from app.security import decode_token


def current_user(
    authorization: str | None = Header(default=None),
    db: Session = Depends(get_db),
) -> User:
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(status_code=401, detail="Missing bearer token")
    token = authorization.split(" ", 1)[1].strip()
    payload = decode_token(token, expected_type="access")
    if not payload or "sub" not in payload:
        raise HTTPException(status_code=401, detail="Invalid or expired token")
    try:
        user_id = int(payload["sub"])
    except (TypeError, ValueError) as exc:
        raise HTTPException(status_code=401, detail="Invalid bearer token") from exc
    user = db.get(User, user_id)
    if user is None:
        raise HTTPException(status_code=401, detail="User no longer exists")
    return user


def completed_profile_user(
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
) -> User:
    if user.role == "student" and db.get(LearnerProfile, user.id) is None:
        raise HTTPException(status_code=409, detail="Complete learner onboarding before continuing")
    return user
