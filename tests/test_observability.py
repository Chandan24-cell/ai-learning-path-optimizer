from __future__ import annotations

import json
import logging
from types import SimpleNamespace

from fastapi.testclient import TestClient

from app.database import get_db


def test_health_readiness_security_headers_and_json_request_log(client: TestClient, caplog) -> None:
    caplog.set_level(logging.INFO, logger="app.requests")
    health = client.get("/health")
    assert health.status_code == 200
    assert health.headers["x-request-id"]
    assert health.headers["content-security-policy"].startswith("default-src 'self'")
    assert health.headers["x-content-type-options"] == "nosniff"
    assert health.headers["x-frame-options"] == "DENY"
    assert health.headers["referrer-policy"] == "strict-origin-when-cross-origin"

    logs = [
        json.loads(record.message) for record in caplog.records if record.name == "app.requests"
    ]
    assert logs
    assert {"request_id", "method", "path", "status", "duration_ms"} <= logs[-1].keys()


def test_ready_reports_database_and_active_mode(client: TestClient, monkeypatch) -> None:
    import app.main as main

    monkeypatch.setattr(main, "get_mode", lambda: "zpd-fallback")
    response = client.get("/ready")
    assert response.status_code == 200
    assert response.json() == {
        "status": "ready",
        "database": "ok",
        "recommender_mode": "zpd-fallback",
    }


def test_ready_reports_unavailable_when_recommender_initialization_fails(
    client: TestClient, monkeypatch
) -> None:
    import app.main as main

    def fail_to_initialize() -> str:
        raise RuntimeError("model files are unavailable")

    monkeypatch.setattr(main, "get_mode", fail_to_initialize)
    response = client.get("/ready")
    assert response.status_code == 503
    assert response.json() == {"detail": "Application is not ready"}


def test_database_dependency_yields_and_closes_session(monkeypatch) -> None:
    import app.database as database_module

    session_stub = SimpleNamespace(closed=False)

    def close_session() -> None:
        session_stub.closed = True

    session_stub.close = close_session
    monkeypatch.setattr(database_module, "SessionLocal", lambda: session_stub)
    session_generator = get_db()
    session = next(session_generator)
    assert not session.closed
    session_generator.close()
    assert session.closed


def test_production_responses_enable_hsts(monkeypatch, client: TestClient) -> None:
    import app.main as main

    monkeypatch.setattr(main, "production", True)
    response = client.get("/health")
    assert response.headers["strict-transport-security"] == (
        "max-age=63072000; includeSubDomains"
    )
