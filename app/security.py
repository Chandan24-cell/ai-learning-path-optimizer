"""Password hashing and signed access/refresh token helpers."""

from __future__ import annotations

import secrets
from datetime import UTC, datetime, timedelta

import bcrypt
import jwt
from jwt import InvalidTokenError

from app.config import settings

ALGORITHM = "HS256"
MAX_PASSWORD_BYTES = 72


def hash_password(raw: str) -> str:
    """Hash a password, rejecting inputs bcrypt cannot represent safely."""
    raw_bytes = raw.encode("utf-8")
    if len(raw_bytes) > MAX_PASSWORD_BYTES:
        raise ValueError("Password must be no more than 72 UTF-8 bytes")
    return bcrypt.hashpw(raw_bytes, bcrypt.gensalt()).decode("utf-8")


def verify_password(raw: str, hashed: str) -> bool:
    raw_bytes = raw.encode("utf-8")
    if len(raw_bytes) > MAX_PASSWORD_BYTES:
        return False
    try:
        return bcrypt.checkpw(raw_bytes, hashed.encode("utf-8"))
    except ValueError, TypeError:
        return False


def create_access_token(subject: str) -> str:
    now = datetime.now(UTC)
    payload = {
        "sub": subject,
        "type": "access",
        "iat": now,
        "exp": now + timedelta(minutes=settings.access_token_minutes),
    }
    return jwt.encode(payload, settings.signing_key, algorithm=ALGORITHM)


def create_refresh_token(subject: str, token_id: str | None = None) -> tuple[str, str, datetime]:
    now = datetime.now(UTC)
    token_id = token_id or secrets.token_urlsafe(32)
    expires_at = now + timedelta(days=settings.refresh_token_days)
    payload = {"sub": subject, "type": "refresh", "jti": token_id, "iat": now, "exp": expires_at}
    token = jwt.encode(payload, settings.signing_key, algorithm=ALGORITHM)
    return token, token_id, expires_at


def decode_token(token: str, expected_type: str | None = "access") -> dict | None:
    try:
        payload = jwt.decode(token, settings.signing_key, algorithms=[ALGORITHM])
    except InvalidTokenError:
        return None
    if expected_type and payload.get("type") != expected_type:
        return None
    return payload
