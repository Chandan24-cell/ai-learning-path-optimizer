from __future__ import annotations

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session, sessionmaker

from app.models_db import Interaction, User
from app.routes.auth import limiter


def test_brute_force_login_is_throttled(client: TestClient, user_factory) -> None:
    user_factory("brute_force")
    limiter.reset()
    responses = [
        client.post(
            "/api/auth/login",
            json={"username": "brute_force", "password": f"Wrong-Password-{index}"},
        )
        for index in range(6)
    ]
    assert [response.status_code for response in responses] == [
        401,
        401,
        401,
        401,
        401,
        429,
    ]


def test_account_deletion_password_guesses_are_rate_limited(
    client: TestClient, user_factory, headers_factory
) -> None:
    auth = user_factory("delete_rate_check")
    limiter.reset()
    responses = [
        client.request(
            "DELETE",
            "/api/account",
            headers=headers_factory(auth),
            json={"password": f"Wrong-Password-{index}"},
        )
        for index in range(6)
    ]
    assert [response.status_code for response in responses] == [401] * 5 + [429]


def test_xss_and_sql_like_inputs_are_safely_serialized_and_ignored(
    client: TestClient,
    user_factory,
    headers_factory,
    database: sessionmaker[Session],
) -> None:
    xss_username = "<script>window.__xss=true</script>"
    rejected = client.post(
        "/api/auth/register",
        json={"username": xss_username, "password": "ValidPassphrase1"},
    )
    assert rejected.status_code == 422
    assert rejected.headers["content-type"].startswith("application/json")
    assert xss_username in rejected.json()["detail"][0]["input"]

    auth = user_factory("safe_history")
    response = client.post(
        "/api/interaction",
        headers=headers_factory(auth),
        json={
            "action": 0,
            "answers": [0, 0, 0],
            "duration": 1.0,
            "topic": "<script>window.__xss=true</script>",
            "resource_type": "' OR 1=1--",
        },
    )
    assert response.status_code == 200
    with database() as db:
        user = db.query(User).filter_by(username="safe_history").one()
        row = db.query(Interaction).filter_by(user_id=user.id).one()
        assert row.topic == "mathematics.algebra"
        assert row.rtype in {"video", "article", "quiz", "interactive", "project"}
    assert "<script>" not in response.text


def test_unknown_account_id_cannot_select_another_users_records(
    client: TestClient,
    user_factory,
    headers_factory,
    database: sessionmaker[Session],
) -> None:
    first_auth = user_factory("id_owner")
    user_factory("id_other")
    with database() as db:
        users = db.query(User).order_by(User.id).all()
        first_id, second_id = (int(user.id) for user in users)
    headers = headers_factory(first_auth)
    for path in (
        f"/api/users/{second_id}",
        f"/api/history/{second_id}",
    ):
        response = client.get(path, headers=headers)
        assert response.status_code == 404
    own_state = client.get("/api/me/state", headers=headers)
    ignored_id = client.get(f"/api/me/state?user_id={second_id}", headers=headers)
    assert own_state.status_code == ignored_id.status_code == 200
    assert own_state.json() == ignored_id.json()
    assert first_id != second_id
