from __future__ import annotations

import json
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta

import jwt
from fastapi.testclient import TestClient

from app.config import settings
from app.models_db import Interaction
from app.routes.auth import limiter


def assert_not_server_error(response, context: str) -> None:
    assert response.status_code < 500, (
        f"{context}: HTTP {response.status_code}: {response.text[:300]}"
    )


def test_empty_missing_wrong_type_and_large_json_bodies(client: TestClient) -> None:
    cases = [
        ("register empty", "post", "/api/auth/register", {}),
        (
            "register missing username",
            "post",
            "/api/auth/register",
            {"password": "ValidPassphrase1"},
        ),
        (
            "register wrong field types",
            "post",
            "/api/auth/register",
            {"username": [], "password": {}},
        ),
        (
            "register unicode username",
            "post",
            "/api/auth/register",
            {"username": "é猫🙂", "password": "ValidPassphrase1"},
        ),
        (
            "register emoji username",
            "post",
            "/api/auth/register",
            {"username": "learner🙂", "password": "ValidPassphrase1"},
        ),
        (
            "register SQL-like username",
            "post",
            "/api/auth/register",
            {"username": "x' OR 1=1--", "password": "ValidPassphrase1"},
        ),
        (
            "register long username",
            "post",
            "/api/auth/register",
            {"username": "u" * 100_000, "password": "ValidPassphrase1"},
        ),
        ("login empty", "post", "/api/auth/login", {}),
        ("refresh empty", "post", "/api/auth/refresh", {}),
        ("logout empty", "post", "/api/auth/logout", {}),
        ("delete empty", "delete", "/api/account", {}),
        ("interaction empty", "post", "/api/interaction", {}),
        ("interaction missing answers", "post", "/api/interaction", {"action": 0, "duration": 1}),
        (
            "interaction wrong field types",
            "post",
            "/api/interaction",
            {"action": "one", "answers": "x", "duration": "long"},
        ),
        (
            "interaction huge answer list",
            "post",
            "/api/interaction",
            {"action": 0, "answers": [0] * 11, "duration": 1},
        ),
    ]
    for label, method, path, body in cases:
        limiter.reset()
        response = client.request(method, path, json=body)
        assert_not_server_error(response, label)

    limiter.reset()
    response = client.post(
        "/api/auth/register",
        content=json.dumps({"username": "largebody", "password": "x" * 1_000_000}),
        headers={"Content-Type": "application/json"},
    )
    assert_not_server_error(response, "one-megabyte JSON body")

    limiter.reset()
    response = client.post(
        "/api/auth/register", content="not-json", headers={"Content-Type": "application/json"}
    )
    assert_not_server_error(response, "malformed JSON")


def test_numeric_query_and_path_boundaries(
    client: TestClient, user_factory, headers_factory
) -> None:
    auth = user_factory("numbers")
    headers = headers_factory(auth)
    for url in (
        "/api/recommend?top_k=-1",
        "/api/recommend?top_k=999999999999999999999999999",
        "/api/recommend?top_k=not-a-number",
        "/api/history?limit=-999999999",
        "/api/history?limit=999999999999999999999999999",
        "/api/history?limit=nope",
        "/api/quiz/999999999999999999999999999",
    ):
        response = client.get(url, headers=headers)
        assert_not_server_error(response, url)
    assert client.get("/api/recommend?top_k=not-a-number", headers=headers).status_code == 422
    assert client.get("/api/history?limit=nope", headers=headers).status_code == 422


def test_missing_expired_tampered_and_wrong_type_tokens_on_protected_routes(
    client: TestClient, user_factory, headers_factory
) -> None:
    auth = user_factory("token_cases")
    expired = jwt.encode(
        {
            "sub": "1",
            "type": "access",
            "exp": datetime.now(UTC) - timedelta(minutes=1),
        },
        settings.signing_key,
        algorithm="HS256",
    )
    for path, method, body in (
        ("/api/account", "delete", {"password": "NotARealPassword123"}),
        ("/api/me/state", "get", None),
        ("/api/recommend", "get", None),
        ("/api/quiz/0", "get", None),
        ("/api/interaction", "post", {"action": 0, "answers": [0, 0, 0], "duration": 1}),
        ("/api/history", "get", None),
    ):
        for label, headers in (
            ("missing", {}),
            ("expired", {"Authorization": f"Bearer {expired}"}),
            ("tampered", {"Authorization": f"Bearer {auth['token']}tampered"}),
            ("wrong token type", {"Authorization": f"Bearer {auth['refresh_token']}"}),
        ):
            response = client.request(method, path, headers=headers, json=body)
            assert_not_server_error(response, f"{label} token {method.upper()} {path}")
            assert response.status_code == 401


def test_quiz_empty_wrong_topic_and_duplicate_submissions(
    client: TestClient, user_factory, headers_factory, database
) -> None:
    auth = user_factory("quiz_edges")
    headers = headers_factory(auth)

    no_answers = client.post(
        "/api/interaction",
        headers=headers,
        json={"action": 0, "answers": [], "duration": 1.0},
    )
    assert_not_server_error(no_answers, "quiz with no answers")
    assert no_answers.status_code == 422

    wrong_topic_answers = client.post(
        "/api/interaction",
        headers=headers,
        json={"action": 5, "answers": [1, 0, 1], "duration": 1.0},
    )
    assert_not_server_error(wrong_topic_answers, "answer indexes valid for another topic")
    assert wrong_topic_answers.status_code == 200
    assert wrong_topic_answers.json()["outcome"]["question_count"] == 3

    payload = {"action": 0, "answers": [1, 0, 1], "duration": 1.0}
    first = client.post("/api/interaction", headers=headers, json=payload)
    second = client.post("/api/interaction", headers=headers, json=payload)
    assert_not_server_error(first, "first duplicate quiz submission")
    assert_not_server_error(second, "second duplicate quiz submission")
    assert first.status_code == second.status_code == 200
    with database() as db:
        assert db.query(Interaction).filter_by(user_id=1).count() == 3


def test_wrong_methods_and_bad_text_body_do_not_return_500(client: TestClient) -> None:
    from app.main import app

    tested: set[tuple[str, str]] = set()
    for route in app.routes:
        path = getattr(route, "path", None)
        methods = getattr(route, "methods", None)
        if not path or not methods or path == "/{path:path}":
            continue
        path = path.replace("{action}", "0").replace("{path:path}", "styles.css")
        for method in ("GET", "POST", "PUT", "PATCH", "DELETE"):
            if method in methods:
                continue
            key = (method, path)
            if key in tested:
                continue
            tested.add(key)
            response = client.request(method, path)
            assert_not_server_error(response, f"wrong method {method} {path}")
    assert tested

    response = client.post(
        "/api/interaction",
        content="<script>alert('validation')</script>",
        headers={"Content-Type": "text/plain"},
    )
    assert_not_server_error(response, "wrong content type")


def test_invalid_refresh_tokens_are_handled_without_server_errors(client: TestClient) -> None:
    for token in ("not-a-token", "tampered.token.value"):
        response = client.post("/api/auth/refresh", json={"refresh_token": token})
        assert_not_server_error(response, "invalid refresh token")
        assert response.status_code == 401
        logout = client.post("/api/auth/logout", json={"refresh_token": token})
        assert_not_server_error(logout, "invalid token during logout")
        assert logout.status_code == 200

    expired = jwt.encode(
        {
            "sub": "1",
            "type": "refresh",
            "jti": "expired-validation-token",
            "exp": datetime.now(UTC) - timedelta(minutes=1),
        },
        settings.signing_key,
        algorithm="HS256",
    )
    response = client.post("/api/auth/refresh", json={"refresh_token": expired})
    assert_not_server_error(response, "expired refresh token")
    assert response.status_code == 401


def test_concurrent_sqlite_quiz_writes(client: TestClient, user_factory, headers_factory) -> None:
    auth = user_factory("parallel_writes")
    headers = headers_factory(auth)

    def submit(index: int) -> int:
        response = client.post(
            "/api/interaction",
            headers=headers,
            json={"action": index % 30, "answers": [0, 0, 0], "duration": 1.0},
        )
        return response.status_code

    with ThreadPoolExecutor(max_workers=20) as pool:
        statuses = list(pool.map(submit, range(60)))
    assert all(status < 500 for status in statuses), f"Concurrent write statuses: {statuses}"
