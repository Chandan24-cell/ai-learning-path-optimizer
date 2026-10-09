from __future__ import annotations

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session, sessionmaker

from app.models_db import Interaction, Question, RefreshToken, StudentState, User


def _answer_key(
    client: TestClient,
    database: sessionmaker[Session],
    headers: dict[str, str],
    action: int,
) -> list[int]:
    quiz_response = client.get(f"/api/quiz/{action}", headers=headers)
    assert quiz_response.status_code == 200, quiz_response.text
    quiz = quiz_response.json()
    with database() as db:
        answers = []
        for question in quiz["questions"]:
            stored = db.get(Question, question["id"])
            assert stored is not None
            answers.append(stored.correct_option)
        return answers


def test_invalid_action_and_duration_limits(
    client: TestClient, user_factory, headers_factory
) -> None:
    auth = user_factory("bounds_user")
    headers = headers_factory(auth)
    assert client.get("/api/quiz/-1", headers=headers).status_code == 400
    assert client.get("/api/quiz/999", headers=headers).status_code == 400
    invalid_submission = client.post(
        "/api/interaction",
        headers=headers,
        json={"action": 999, "answers": [0, 0, 0], "duration": 1.0},
    )
    assert invalid_submission.status_code == 400

    for duration in (0.49, 120.01):
        result = client.post(
            "/api/interaction",
            headers=headers,
            json={"action": 0, "answers": [0, 0, 0], "duration": duration},
        )
        assert result.status_code == 422


def test_server_grades_answers_ignores_client_score_and_updates_state(
    client: TestClient,
    database: sessionmaker[Session],
    user_factory,
    headers_factory,
    test_catalog: list[dict],
    monkeypatch,
) -> None:
    auth = user_factory("grade_user")
    headers = headers_factory(auth)
    answers = _answer_key(client, database, headers, 0)

    result = client.post(
        "/api/interaction",
        headers=headers,
        json={"action": 0, "answers": answers, "duration": 2.0, "score": 0},
    )
    assert result.status_code == 200, result.text
    assert result.json()["outcome"]["score"] == 100.0
    assert result.json()["state"]["n_interactions"] == 1
    assert result.json()["state"]["attempts"][test_catalog[0]["topic"]] == 1

    history = client.get("/api/history", headers=headers)
    assert history.status_code == 200
    assert len(history.json()["history"]) == 1
    assert history.json()["history"][0]["score"] == 100.0


def test_catalog_meta_recommendations_and_missing_state_recovery(
    client: TestClient,
    database: sessionmaker[Session],
    user_factory,
    headers_factory,
    test_catalog: list[dict],
    monkeypatch,
) -> None:
    auth = user_factory("catalog_user")
    headers = headers_factory(auth)
    assert client.get("/api/meta").json()["recommender_mode"] in {"hybrid", "zpd-fallback"}
    assert len(client.get("/api/catalog").json()["catalog"]) >= 10
    quiz = client.get("/api/quiz/0", headers=headers)
    assert quiz.status_code == 200
    assert len(quiz.json()["questions"]) == 3
    assert client.get("/api/recommend?top_k=1", headers=headers).json()["recommendations"]

    with database() as db:
        user = db.query(User).filter_by(username="catalog_user").one()
        db.query(StudentState).filter_by(user_id=user.id).delete()
        db.commit()
        user_id = user.id
    state = client.get("/api/me/state", headers=headers)
    assert state.status_code == 200
    assert state.json()["n_interactions"] == 0
    with database() as db:
        assert db.query(StudentState).filter_by(user_id=user_id).count() == 1


def test_users_cannot_read_or_change_other_user_data(
    client: TestClient,
    database: sessionmaker[Session],
    user_factory,
    headers_factory,
    test_catalog: list[dict],
    monkeypatch,
) -> None:
    user_a = user_factory("learner_a")
    user_factory("learner_b")
    with database() as db:
        b = db.query(User).filter_by(username="learner_b").one()
        db.add(
            Interaction(
                user_id=b.id,
                action=0,
                topic="Private topic",
                rtype="quiz",
                difficulty=2,
                duration=4,
                score=75,
                gain=0.1,
                engagement=0.5,
            )
        )
        before = db.query(StudentState).filter_by(user_id=b.id).one().mastery_est_json
        db.commit()
        b_id = b.id

    headers_a = headers_factory(user_a)
    assert client.get("/api/history", headers=headers_a).json()["history"] == []
    mutation = client.post(
        "/api/interaction",
        headers=headers_a,
        json={
            "action": 0,
            "answers": _answer_key(client, database, headers_a, 0),
            "duration": 2.0,
        },
    )
    assert mutation.status_code == 200
    with database() as db:
        after = db.query(StudentState).filter_by(user_id=b_id).one().mastery_est_json
        assert after == before
        assert db.query(Interaction).filter_by(user_id=b_id).one().topic == "Private topic"


def test_delete_account_removes_user_and_related_rows(
    client: TestClient, database: sessionmaker[Session], user_factory, headers_factory
) -> None:
    auth = user_factory("delete_me")
    with database() as db:
        user_id = db.query(User).filter_by(username="delete_me").one().id
        db.add(
            Interaction(
                user_id=user_id,
                action=0,
                topic="Algebra",
                rtype="quiz",
                difficulty=2,
                duration=1,
                score=50,
                gain=0,
                engagement=0.5,
            )
        )
        db.commit()

    response = client.request(
        "DELETE",
        "/api/account",
        headers=headers_factory(auth),
        json={"password": "Strong-Test-Pass1"},
    )
    assert response.status_code == 200
    with database() as db:
        assert db.query(User).filter_by(id=user_id).count() == 0
        assert db.query(StudentState).filter_by(user_id=user_id).count() == 0
        assert db.query(Interaction).filter_by(user_id=user_id).count() == 0
        assert db.query(RefreshToken).filter_by(user_id=user_id).count() == 0
