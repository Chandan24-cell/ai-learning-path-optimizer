from __future__ import annotations

from datetime import UTC, datetime, timedelta

import jwt
import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from app.config import Settings, settings
from app.models_db import Enrollment, RefreshToken, User
from app.schemas import LoginIn, RegisterIn
from app.security import hash_password, verify_password


def test_register_duplicate_weak_password_and_login(client: TestClient, database) -> None:
    weak = client.post("/api/auth/register", json={"username": "weak", "password": "1234567890"})
    assert weak.status_code == 422

    created = client.post(
        "/api/auth/register", json={"username": "  Alice_01 ", "password": "Strong-Test-Pass1"}
    )
    assert created.status_code == 200
    assert created.json()["username"] == "alice_01"
    assert created.json()["refresh_token"]
    with database() as db:
        user = db.query(User).filter_by(username="alice_01").one()
        assert user.active_subject_id is None
        assert db.query(Enrollment).filter_by(user_id=user.id).count() == 0

    duplicate = client.post(
        "/api/auth/register", json={"username": "ALICE_01", "password": "Another-Valid-Pass2"}
    )
    assert duplicate.status_code == 409
    invalid_username = client.post(
        "/api/auth/register", json={"username": "bad-name", "password": "Another-Valid-Pass2"}
    )
    assert invalid_username.status_code == 422
    oversized = client.post(
        "/api/auth/register", json={"username": "oversized", "password": "é" * 37}
    )
    assert oversized.status_code == 422

    login = client.post(
        "/api/auth/login", json={"username": " Alice_01", "password": "Strong-Test-Pass1"}
    )
    assert login.status_code == 200
    wrong_password = client.post(
        "/api/auth/login", json={"username": "alice_01", "password": "Wrong-Password-99"}
    )
    assert wrong_password.status_code == 401


def test_rate_limit_is_five_logins_per_minute(client: TestClient, user_factory) -> None:
    user_factory("rate_test")
    statuses = [
        client.post(
            "/api/auth/login", json={"username": "rate_test", "password": "Bad-Password-123"}
        ).status_code
        for _ in range(6)
    ]
    assert statuses == [401, 401, 401, 401, 401, 429]


def test_refresh_then_logout_revokes_refresh_token(client: TestClient, user_factory) -> None:
    auth = user_factory("refresh_user")
    refreshed = client.post("/api/auth/refresh", json={"refresh_token": auth["refresh_token"]})
    assert refreshed.status_code == 200
    assert refreshed.json()["refresh_token"] != auth["refresh_token"]
    assert (
        client.post("/api/auth/refresh", json={"refresh_token": auth["refresh_token"]}).status_code
        == 401
    )

    logout = client.post(
        "/api/auth/logout", json={"refresh_token": refreshed.json()["refresh_token"]}
    )
    assert logout.status_code == 200
    refused = client.post(
        "/api/auth/refresh", json={"refresh_token": refreshed.json()["refresh_token"]}
    )
    assert refused.status_code == 401


def test_expired_and_bad_access_tokens_are_refused(client: TestClient) -> None:
    expired = jwt.encode(
        {
            "sub": "1",
            "type": "access",
            "exp": datetime.now(UTC) - timedelta(minutes=1),
        },
        settings.signing_key,
        algorithm="HS256",
    )
    for token in (expired, "not-a-signed-token"):
        response = client.get("/api/me/state", headers={"Authorization": f"Bearer {token}"})
        assert response.status_code == 401


def test_missing_and_malformed_authorization_are_refused(client: TestClient) -> None:
    assert client.get("/api/me/state").status_code == 401
    assert client.get("/api/me/state", headers={"Authorization": "Basic wrong"}).status_code == 401

    malformed_subject = jwt.encode(
        {"sub": "not-an-id", "type": "access", "exp": datetime.now(UTC) + timedelta(minutes=1)},
        settings.signing_key,
        algorithm="HS256",
    )
    assert (
        client.get(
            "/api/me/state", headers={"Authorization": f"Bearer {malformed_subject}"}
        ).status_code
        == 401
    )


def test_config_and_password_boundary_validation() -> None:
    for secret in (None, "short", "dev-only-secret-change-in-production-xyz"):
        with pytest.raises(ValidationError):
            Settings(_env_file=None, app_env="production", app_secret=secret)
    production = Settings(
        _env_file=None,
        app_env="production",
        app_secret="this-is-a-valid-production-secret-32-bytes",
        allowed_origins=["https://learning-path.example"],
    )
    assert production.app_env == "production"
    with pytest.raises(ValidationError):
        Settings(_env_file=None, app_env="staging")
    with pytest.raises(ValidationError):
        RegisterIn(username="ab", password="Valid-Password-123")
    with pytest.raises(ValidationError):
        LoginIn(username="user name", password="some-password")
    with pytest.raises(ValueError, match="72 UTF-8 bytes"):
        hash_password("x" * 73)
    assert not verify_password("x" * 73, "not-a-bcrypt-hash")


def test_token_records_are_scoped_to_the_test_database(client: TestClient, database) -> None:
    client.post(
        "/api/auth/register", json={"username": "stored_user", "password": "Strong-Test-Pass1"}
    ).json()
    with database() as db:
        assert db.query(User).count() == 1
        assert db.query(RefreshToken).count() == 1
