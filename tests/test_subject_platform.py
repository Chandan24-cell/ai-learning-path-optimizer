from __future__ import annotations

import json
from pathlib import Path

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session, sessionmaker

from app.content.pack import import_content_pack
from app.models_db import (
    Enrollment,
    Question,
    Resource,
    StudentState,
    Subject,
    Topic,
    TopicPrerequisite,
    User,
)
from app.services.subject_enrollment import enroll_user


def _seed_networking_subject(database, user_id: int, subject_id: str) -> None:
    fixture = json.loads(
        (Path(__file__).parent / "fixtures" / "computer_networking_sources.json").read_text()
    )
    with database() as db:
        subject = Subject(
            id=subject_id,
            name=fixture["subject"],
            description="Saved Wikipedia fixture for source-grounded quiz tests.",
            source="discovered",
            status="draft",
            created_by=user_id,
            source_url=fixture["source_url"],
        )
        db.add(subject)
        db.flush()
        previous_topic_id = None
        for index, item in enumerate(fixture["topics"], start=1):
            slug = f"{index}-{item['name'].lower().replace(' ', '-')}"
            topic_id = f"{subject_id}.{slug}"
            topic = Topic(
                id=topic_id,
                subject_id=subject_id,
                slug=slug,
                name=item["name"],
                order=index,
                source_url=fixture["source_url"],
                source_extract=item["summary"],
                provenance=json.dumps({"linked_terms": item["linked_terms"]}),
            )
            db.add(topic)
            db.flush()
            if previous_topic_id:
                db.add(
                    TopicPrerequisite(
                        topic_id=topic_id,
                        prerequisite_topic_id=previous_topic_id,
                    )
                )
            previous_topic_id = topic_id
            db.add(
                Resource(
                    id=f"{topic_id}.reference-1",
                    topic_id=topic_id,
                    type="article",
                    title=f"Wikipedia: {item['name']}",
                    difficulty=float(index),
                    duration=15,
                    url=fixture["source_url"],
                    source_url=fixture["source_url"],
                )
            )
        db.flush()
        user = db.get(User, user_id)
        assert user is not None
        enroll_user(db, user, subject, "beginner")


def test_subject_enrollment_diagnostic_state_and_history_are_isolated(
    client: TestClient,
    database: sessionmaker[Session],
    user_factory,
    headers_factory,
) -> None:
    auth = user_factory("multi_subject_student")
    headers = headers_factory(auth)
    subjects = client.get("/api/subjects?include_samples=true").json()["subjects"]
    assert {subject["id"] for subject in subjects} >= {
        "mathematics",
        "physics",
        "python-programming",
    }

    enrolled = client.post("/api/subjects/physics/enroll", headers=headers)
    assert enrolled.status_code == 200
    assert enrolled.json()["diagnostic_required"] is True
    assert client.get("/api/subjects/physics/recommendations", headers=headers).status_code == 409

    diagnostic = client.get("/api/subjects/physics/diagnostic", headers=headers)
    assert diagnostic.status_code == 200
    questions = diagnostic.json()["questions"]
    assert questions == []
    assert "limited quiz banks" in diagnostic.json()["message"]
    with database() as db:
        math_state_before = (
            db.query(StudentState)
            .join(User, StudentState.user_id == User.id)
            .filter(
                User.username == "multi_subject_student", StudentState.subject_id == "mathematics"
            )
            .one()
            .mastery_est_json
        )
    completed = client.post(
        "/api/subjects/physics/diagnostic",
        headers=headers,
        json={"answers": {}, "session_id": diagnostic.json()["session_id"]},
    )
    assert completed.status_code == 200, completed.text
    assert completed.json()["progress"]["diagnostic_completed"] is True
    recommendations = client.get("/api/subjects/physics/recommendations", headers=headers)
    assert recommendations.status_code == 200
    assert recommendations.json()["recommendations"] == []
    assert recommendations.json()["message"]
    assert client.get("/api/subjects/physics/history", headers=headers).json()["history"] == []
    assert client.get("/api/subjects/mathematics/history", headers=headers).json()["history"] == []

    with database() as db:
        user = db.query(User).filter_by(username="multi_subject_student").one()
        math_state_after = (
            db.query(StudentState)
            .filter_by(user_id=user.id, subject_id="mathematics")
            .one()
            .mastery_est_json
        )
        assert math_state_before == math_state_after
        assert (
            db.query(StudentState)
            .filter_by(user_id=user.id, subject_id="physics")
            .one()
            .n_interactions
            == 0
        )
        assert (
            db.query(Enrollment)
            .filter_by(user_id=user.id, subject_id="physics")
            .one()
            .diagnostic_completed
        )

    switched = client.put(
        "/api/me/subject",
        headers=headers,
        json={"subject_id": "mathematics"},
    )
    assert switched.status_code == 200
    assert (
        client.get("/api/me/subjects", headers=headers).json()["active_subject_id"] == "mathematics"
    )


def test_teacher_can_add_question_but_student_cannot(
    client: TestClient,
    database: sessionmaker[Session],
    user_factory,
    headers_factory,
) -> None:
    student_headers = headers_factory(user_factory("content_student"))
    teacher = client.post(
        "/api/auth/register",
        json={
            "username": "content_teacher",
            "password": "Strong-Test-Pass1",
            "role": "teacher",
        },
    )
    assert teacher.status_code == 200, teacher.text
    teacher_headers = headers_factory(teacher.json())
    with database() as db:
        topic_id = db.query(Topic).filter_by(subject_id="mathematics").first().id
    payload = {
        "id": "teacher-authored-item",
        "difficulty": 3,
        "text": "Which value is prime?",
        "options": ["9", "11", "15"],
        "correct_option": 1,
        "explanation": "11 has no positive divisors other than 1 and itself.",
    }
    path = f"/api/teacher/topics/{topic_id}/questions"
    denied = client.post(path, headers=student_headers, json=payload)
    assert denied.status_code == 403
    created = client.post(path, headers=teacher_headers, json=payload)
    assert created.status_code == 200, created.text
    updated = client.patch(
        f"/api/teacher/questions/{created.json()['id']}",
        headers=teacher_headers,
        json={
            "explanation": "11 is divisible only by 1 and 11.",
            "status": "approved",
        },
    )
    assert updated.status_code == 200, updated.text
    with database() as db:
        assert db.get(Question, created.json()["id"]).status == "teacher-approved"


def test_adaptive_questions_are_hidden_tracked_non_repeating_and_reportable(
    client: TestClient,
    database: sessionmaker[Session],
    user_factory,
    headers_factory,
) -> None:
    auth = user_factory("adaptive_quiz_student")
    headers = headers_factory(auth)
    with database() as db:
        user = db.query(User).filter_by(username="adaptive_quiz_student").one()
        subject_id = f"fixture-networking-{user.id}"
        user_id = user.id
    _seed_networking_subject(database, user_id, subject_id)
    diagnostic = client.get(f"/api/subjects/{subject_id}/diagnostic", headers=headers).json()
    with database() as db:
        answers = {
            question["id"]: db.get(Question, question["id"]).correct_option
            for question in diagnostic["questions"]
        }
    completed = client.post(
        f"/api/subjects/{subject_id}/diagnostic",
        headers=headers,
        json={"answers": answers, "session_id": diagnostic["session_id"]},
    )
    assert completed.status_code == 200, completed.text

    recommendations = client.get(
        f"/api/subjects/{subject_id}/recommendations", headers=headers
    ).json()["recommendations"]
    activity = client.get(
        f"/api/subjects/{subject_id}/resources/{recommendations[0]['resource_id']}/quiz",
        headers=headers,
    )
    assert activity.status_code == 200, activity.text
    quiz = activity.json()
    assert len(quiz["questions"]) == 1
    first = quiz["questions"][0]
    assert "correct_option" not in first
    with database() as db:
        correct = db.get(Question, first["id"]).correct_option
    wrong = (correct + 1) % len(first["options"])
    submitted = client.post(
        f"/api/subjects/{subject_id}/quiz-sessions/{quiz['session_id']}/answer",
        headers=headers,
        json={"question_id": first["id"], "answer": wrong, "duration": 1.0},
    )
    assert submitted.status_code == 200, submitted.text
    result = submitted.json()
    assert result["feedback"]["correct"] is False
    assert result["feedback"]["source_sentence"]
    assert result["next_question"] is not None, result
    assert result["next_question"]["id"] != first["id"]

    other_headers = headers_factory(user_factory("adaptive_quiz_other"))
    denied = client.post(
        f"/api/subjects/{subject_id}/quiz-sessions/{quiz['session_id']}/answer",
        headers=other_headers,
        json={
            "question_id": result["next_question"]["id"],
            "answer": 0,
            "duration": 1.0,
        },
    )
    assert denied.status_code == 404
    report = client.post(
        f"/api/subjects/{subject_id}/questions/{first['id']}/report",
        headers=headers,
        json={"reason": "ambiguous", "details": "Please review this option."},
    )
    assert report.status_code == 200, report.text
    teacher_auth = client.post(
        "/api/auth/register",
        json={
            "username": "adaptive_quiz_teacher",
            "password": "Strong-Test-Pass1",
            "role": "teacher",
        },
    )
    assert teacher_auth.status_code == 200, teacher_auth.text
    teacher_headers = headers_factory(teacher_auth.json())
    reports = client.get("/api/teacher/question-reports", headers=teacher_headers)
    assert reports.status_code == 200, reports.text
    matching_report = next(
        item for item in reports.json()["reports"] if item["id"] == report.json()["report_id"]
    )
    assert matching_report["status"] == "open"
    reviewed = client.patch(
        f"/api/teacher/question-reports/{matching_report['id']}",
        headers=teacher_headers,
        json={"status": "reviewed"},
    )
    assert reviewed.status_code == 200, reviewed.text
    assert reviewed.json()["status"] == "reviewed"
    duplicate = client.post(
        f"/api/subjects/{subject_id}/quiz-sessions/{quiz['session_id']}/answer",
        headers=headers,
        json={"question_id": first["id"], "answer": wrong, "duration": 1.0},
    )
    assert duplicate.status_code == 409
    deleted = client.delete(f"/api/teacher/questions/{first['id']}", headers=teacher_headers)
    assert deleted.status_code == 200, deleted.text


def test_new_content_pack_imports_without_code_changes(
    client: TestClient,
    database: sessionmaker[Session],
    tmp_path: Path,
) -> None:
    source = (
        Path(__file__).resolve().parents[1]
        / "content"
        / "examples"
        / "python-programming"
        / "content.json"
    )
    pack = json.loads(source.read_text(encoding="utf-8"))
    pack["slug"] = "custom-study-subject"
    pack["name"] = "Custom Study Subject"
    target = tmp_path / "content.json"
    target.write_text(json.dumps(pack), encoding="utf-8")

    with database() as db:
        first = import_content_pack(target, db)
        second = import_content_pack(target, db)
        assert first == second
        assert db.query(StudentState).filter_by(subject_id="custom-study-subject").count() == 0

    subjects = client.get("/api/subjects").json()["subjects"]
    assert any(subject["id"] == "custom-study-subject" for subject in subjects)
