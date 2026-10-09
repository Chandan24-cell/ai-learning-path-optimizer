"""Registration, login, refresh-token, logout, and account deletion endpoints."""

from __future__ import annotations

from typing import Literal, cast

from fastapi import APIRouter, Depends, HTTPException, Request
from slowapi import Limiter
from slowapi.util import get_remote_address
from sqlalchemy import func, or_
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.database import get_db
from app.dependencies import current_user
from app.models_db import (
    Enrollment,
    Interaction,
    LearnerProfile,
    Question,
    RefreshToken,
    Resource,
    StudentState,
    Subject,
    Topic,
    TopicPrerequisite,
    User,
)
from app.schemas import (
    DeleteAccountIn,
    LoginIn,
    LogoutIn,
    RefreshIn,
    RegisterIn,
    TokenOut,
)
from app.security import (
    create_access_token,
    create_refresh_token,
    decode_token,
    hash_password,
    verify_password,
)

limiter = Limiter(key_func=get_remote_address)
router = APIRouter(prefix="/api/auth", tags=["auth"])
account_router = APIRouter(prefix="/api", tags=["account"])


def _issue_tokens(user: User, db: Session) -> TokenOut:
    if user.role not in ("student", "teacher"):
        raise ValueError(f"Unsupported user role: {user.role}")
    refresh, token_id, expires_at = create_refresh_token(str(user.id))
    db.add(RefreshToken(id=token_id, user_id=user.id, expires_at=expires_at))
    return TokenOut(
        token=create_access_token(str(user.id)),
        refresh_token=refresh,
        username=user.username,
        role=cast(Literal["student", "teacher"], user.role),
    )


@router.post("/register", response_model=TokenOut)
@limiter.limit("5/minute")
def register(request: Request, payload: RegisterIn, db: Session = Depends(get_db)):
    user = User(
        username=payload.username,
        hashed_password=hash_password(payload.password),
        role=payload.role,
    )
    try:
        db.add(user)
        db.flush()
        response = _issue_tokens(user, db)
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(status_code=409, detail="Username is already taken") from exc
    return response


@router.post("/login", response_model=TokenOut)
@limiter.limit("5/minute")
def login(request: Request, payload: LoginIn, db: Session = Depends(get_db)):
    user = db.query(User).filter(func.lower(User.username) == payload.username).first()
    if not user or not verify_password(payload.password, user.hashed_password):
        raise HTTPException(status_code=401, detail="Invalid credentials")
    response = _issue_tokens(user, db)
    db.commit()
    return response


@router.post("/refresh", response_model=TokenOut)
def refresh(payload: RefreshIn, db: Session = Depends(get_db)):
    claims = decode_token(payload.refresh_token, expected_type="refresh")
    if not claims or not claims.get("jti") or not claims.get("sub"):
        raise HTTPException(status_code=401, detail="Invalid or expired refresh token")
    stored = db.get(RefreshToken, claims["jti"])
    if stored is None or stored.revoked or str(stored.user_id) != str(claims["sub"]):
        raise HTTPException(status_code=401, detail="Refresh token has been revoked")
    user = db.get(User, stored.user_id)
    if user is None:
        raise HTTPException(status_code=401, detail="User no longer exists")
    stored.revoked = True
    response = _issue_tokens(user, db)
    db.commit()
    return response


@router.post("/logout")
def logout(payload: LogoutIn, db: Session = Depends(get_db)):
    claims = decode_token(payload.refresh_token, expected_type="refresh")
    if claims and claims.get("jti"):
        stored = db.get(RefreshToken, claims["jti"])
        if stored is not None:
            stored.revoked = True
            db.commit()
    return {"status": "logged out"}


@account_router.delete("/account")
@limiter.limit("5/minute")
def delete_account(
    request: Request,
    payload: DeleteAccountIn,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
):
    if not verify_password(payload.password, user.hashed_password):
        raise HTTPException(status_code=401, detail="Password confirmation failed")
    db.query(Interaction).filter(Interaction.user_id == user.id).delete(synchronize_session=False)
    db.query(LearnerProfile).filter(LearnerProfile.user_id == user.id).delete(
        synchronize_session=False
    )
    db.query(StudentState).filter(StudentState.user_id == user.id).delete(synchronize_session=False)
    db.query(Enrollment).filter(Enrollment.user_id == user.id).delete(synchronize_session=False)
    db.query(RefreshToken).filter(RefreshToken.user_id == user.id).delete(synchronize_session=False)
    owned_subject_ids = [
        subject_id
        for (subject_id,) in db.query(Subject.id).filter(Subject.created_by == user.id).all()
    ]
    if owned_subject_ids:
        owned_topic_ids = [
            topic_id
            for (topic_id,) in db.query(Topic.id)
            .filter(Topic.subject_id.in_(owned_subject_ids))
            .all()
        ]
        if owned_topic_ids:
            db.query(TopicPrerequisite).filter(
                or_(
                    TopicPrerequisite.topic_id.in_(owned_topic_ids),
                    TopicPrerequisite.prerequisite_topic_id.in_(owned_topic_ids),
                )
            ).delete(synchronize_session=False)
            db.query(Question).filter(Question.topic_id.in_(owned_topic_ids)).delete(
                synchronize_session=False
            )
            db.query(Resource).filter(Resource.topic_id.in_(owned_topic_ids)).delete(
                synchronize_session=False
            )
            db.query(Topic).filter(Topic.id.in_(owned_topic_ids)).delete(synchronize_session=False)
        db.query(Subject).filter(Subject.id.in_(owned_subject_ids)).delete(
            synchronize_session=False
        )
    db.delete(user)
    db.commit()
    return {"status": "account and associated data deleted"}
