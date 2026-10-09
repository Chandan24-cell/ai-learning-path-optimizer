from __future__ import annotations

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session, sessionmaker

from app.models_db import LearnerProfile, Question, StudentState, User

PROFILE = {
    "country": "IN",
    "language": "English",
    "education_level": "high_school",
    "institution_type": "school",
    "grade_year": "Grade 10",
    "curriculum_program": "CBSE",
    "field_of_study": "Science",
    "learning_goal": "exam",
    "weekly_time_hours": 5,
    "learning_style": "examples",
    "prior_experience": "some",
    "consent": True,
}


def _headers(auth: dict) -> dict[str, str]:
    return {"Authorization": f"Bearer {auth['token']}"}


def test_registration_requires_onboarding_and_profile_initializes_subject_level(
    client: TestClient, database: sessionmaker[Session]
) -> None:
    auth_response = client.post(
        "/api/auth/register",
        json={"username": "profile_student", "password": "Strong-Test-Pass1"},
    )
    assert auth_response.status_code == 200, auth_response.text
    auth = auth_response.json()
    headers = _headers(auth)

    status = client.get("/api/me/profile", headers=headers)
    assert status.status_code == 200
    assert status.json() == {"required": True, "completed": False, "profile": None}
    assert client.get("/api/me/state", headers=headers).status_code == 409
    assert client.get("/api/me/subjects", headers=headers).status_code == 409

    options = client.get("/api/onboarding/options")
    assert options.status_code == 200
    assert "JEE track" in next(
        item["curricula"] for item in options.json()["countries"] if item["id"] == "IN"
    )
    assert "Common Core" in next(
        item["curricula"] for item in options.json()["countries"] if item["id"] == "US"
    )
    assert "International Baccalaureate (IB)" in next(
        item["curricula"] for item in options.json()["countries"] if item["id"] == "GB"
    )
    assert "age" not in options.json()
    assert "date_of_birth" not in options.json()

    not_consented = {**PROFILE, "consent": False}
    assert client.put("/api/me/profile", headers=headers, json=not_consented).status_code == 422
    invalid_curriculum = {**PROFILE, "curriculum_program": "Unlisted curriculum"}
    invalid_response = client.put("/api/me/profile", headers=headers, json=invalid_curriculum)
    assert invalid_response.status_code == 422

    saved = client.put("/api/me/profile", headers=headers, json=PROFILE)
    assert saved.status_code == 200, saved.text
    assert saved.json()["completed"] is True
    assert saved.json()["profile"]["country"] == "IN"
    assert client.get("/api/me/state", headers=headers).status_code == 409
    assert client.post("/api/subjects/mathematics/enroll", headers=headers).status_code == 200
    state = client.get("/api/me/state", headers=headers)
    assert state.status_code == 200
    assert state.json()["learner_level"] == 40
    assert state.json()["learner_level_label"] == "high_school"
    assert state.json()["learning_goal"] == "exam"

    enrolled = client.post("/api/subjects/physics/enroll", headers=headers)
    assert enrolled.status_code == 200, enrolled.text
    with database() as db:
        user = db.query(User).filter_by(username="profile_student").one()
        physics_state = db.get(StudentState, (user.id, "physics"))
        assert physics_state is not None
        assert physics_state.learner_level == 40
        assert physics_state.learning_goal == "exam"


def test_empty_source_diagnostic_keeps_level_and_profile_edit_applies_to_each_subject(
    client: TestClient,
    database: sessionmaker[Session],
) -> None:
    auth = client.post(
        "/api/auth/register",
        json={"username": "level_student", "password": "Strong-Test-Pass1"},
    ).json()
    headers = _headers(auth)
    assert client.put("/api/me/profile", headers=headers, json=PROFILE).status_code == 200
    assert client.post("/api/subjects/mathematics/enroll", headers=headers).status_code == 200
    questions_response = client.get("/api/subjects/mathematics/diagnostic", headers=headers)
    assert questions_response.status_code == 200
    questions = questions_response.json()["questions"]
    assert not questions
    with database() as db:
        answers = {
            question["id"]: db.get(Question, question["id"]).correct_option
            for question in questions
        }
    completed = client.post(
        "/api/subjects/mathematics/diagnostic",
        headers=headers,
        json={"answers": answers, "session_id": questions_response.json()["session_id"]},
    )
    assert completed.status_code == 200, completed.text
    state = completed.json()["progress"]
    assert state["learner_level"] == 40
    assert state["learner_level_label"] == "high_school"

    assert client.post("/api/subjects/physics/enroll", headers=headers).status_code == 200
    updated_profile = {
        **PROFILE,
        "education_level": "postgraduate",
        "learning_goal": "career",
        "curriculum_program": None,
    }
    updated = client.put("/api/me/profile", headers=headers, json=updated_profile)
    assert updated.status_code == 200, updated.text
    with database() as db:
        user = db.query(User).filter_by(username="level_student").one()
        states = db.query(StudentState).filter_by(user_id=user.id).all()
        state_values = {
            (row.learner_level, row.learner_level_label, row.learning_goal) for row in states
        }
        assert state_values == {(75, "postgraduate", "career")}


def test_profile_can_be_deleted_and_account_deletion_removes_profile(
    client: TestClient,
    database: sessionmaker[Session],
) -> None:
    auth = client.post(
        "/api/auth/register",
        json={"username": "profile_delete", "password": "Strong-Test-Pass1"},
    ).json()
    headers = _headers(auth)
    assert client.put("/api/me/profile", headers=headers, json=PROFILE).status_code == 200
    assert client.delete("/api/me/profile", headers=headers).json() == {
        "status": "profile deleted",
        "onboarding_required": True,
    }
    assert client.get("/api/me/state", headers=headers).status_code == 409

    assert client.put("/api/me/profile", headers=headers, json=PROFILE).status_code == 200
    deleted = client.request(
        "DELETE",
        "/api/account",
        headers=headers,
        json={"password": "Strong-Test-Pass1"},
    )
    assert deleted.status_code == 200
    with database() as db:
        assert db.query(LearnerProfile).count() == 0
