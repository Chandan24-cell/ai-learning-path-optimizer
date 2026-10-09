"""Test fixtures. App imports are isolated from the user's real database."""

from __future__ import annotations

import os
import tempfile
from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event
from sqlalchemy.orm import Session, sessionmaker

_BOOTSTRAP_DIR = Path(tempfile.mkdtemp(prefix="learning-path-pytest-bootstrap-"))
os.environ["APP_ENV"] = "development"
os.environ["APP_SECRET"] = "pytest-only-secret-that-is-at-least-32-bytes"
os.environ["DATABASE_URL"] = f"sqlite:///{_BOOTSTRAP_DIR / 'bootstrap.db'}"
os.environ["ALLOWED_ORIGINS"] = "http://127.0.0.1,http://localhost"

from app.content.pack import import_content_pack  # noqa: E402
from app.database import Base, get_db  # noqa: E402
from app.main import app  # noqa: E402
from app.models_db import Interaction, RefreshToken, StudentState, User  # noqa: E402,F401
from app.routes.auth import limiter  # noqa: E402
from src.domain import get_domain  # noqa: E402


@pytest.fixture
def database(tmp_path: Path) -> Iterator[sessionmaker[Session]]:
    """Create a new temporary SQLite database for each test."""
    engine = create_engine(
        f"sqlite:///{tmp_path / 'test.db'}",
        connect_args={"check_same_thread": False},
        future=True,
    )

    @event.listens_for(engine, "connect")
    def _enable_foreign_keys(connection, _record) -> None:
        cursor = connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)
    with factory() as db:
        from app.content.catalog import scan_content_packs

        entries, _ = scan_content_packs(include_examples=True)
        for entry in entries:
            import_content_pack(entry.path, db)
    try:
        yield factory
    finally:
        engine.dispose()


@pytest.fixture
def client(database: sessionmaker[Session]) -> Iterator[TestClient]:
    """API client wired only to that test's temporary database."""

    def override_get_db() -> Iterator[Session]:
        with database() as db:
            yield db

    app.dependency_overrides[get_db] = override_get_db
    limiter.reset()
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()
    limiter.reset()


@pytest.fixture(autouse=True)
def disable_live_discovery(monkeypatch: pytest.MonkeyPatch) -> None:
    """Keep provider calls deterministic unless a test supplies saved responses."""
    import app.routes.discovery as discovery_routes

    with discovery_routes._request_lock:
        discovery_routes._request_times.clear()

    class OfflineDiscovery:
        def search(self, _query: str, _level: str):
            return [], ["Public sources are unavailable in unit tests."]

    monkeypatch.setattr(discovery_routes, "_service", OfflineDiscovery())


@pytest.fixture
def test_catalog() -> list[dict]:
    return get_domain()[0]


@pytest.fixture
def user_factory(client: TestClient):
    def create_user(username: str, password: str = "Strong-Test-Pass1") -> dict:
        response = client.post(
            "/api/auth/register", json={"username": username, "password": password}
        )
        assert response.status_code == 200, response.text
        auth = response.json()
        profile_response = client.put(
            "/api/me/profile",
            headers={"Authorization": f"Bearer {auth['token']}"},
            json={
                "country": "IN",
                "language": "English",
                "education_level": "middle_school",
                "institution_type": "self_study",
                "grade_year": "Year 7",
                "curriculum_program": None,
                "field_of_study": "General studies",
                "learning_goal": "skill",
                "weekly_time_hours": 3,
                "learning_style": "mixed",
                "prior_experience": "new",
                "consent": True,
            },
        )
        assert profile_response.status_code == 200, profile_response.text
        enrollment_response = client.post(
            "/api/subjects/mathematics/enroll",
            headers={"Authorization": f"Bearer {auth['token']}"},
            json={"target_depth": "beginner"},
        )
        assert enrollment_response.status_code == 200, enrollment_response.text
        return auth

    return create_user


@pytest.fixture
def headers_factory():
    def make_headers(auth: dict) -> dict[str, str]:
        return {"Authorization": f"Bearer {auth['token']}"}

    return make_headers
