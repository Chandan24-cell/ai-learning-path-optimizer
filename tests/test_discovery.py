from __future__ import annotations

import pytest
from sqlalchemy.orm import Session, sessionmaker

from app.models_db import Enrollment, Resource, Subject, Topic, TopicPrerequisite, User
from app.services.discovery.interfaces import Candidate
from app.services.discovery.safety import (
    DiscoveryUnavailable,
    _verify_public_dns,
    validate_provider_url,
)


def test_enrollment_limit_and_unenrollment_free_a_slot(
    client, user_factory, headers_factory, monkeypatch
):
    import app.routes.discovery as discovery_routes

    monkeypatch.setattr(discovery_routes._service, "search", lambda _query, _level: ([], []))
    auth = user_factory("subject_limit_student")
    headers = headers_factory(auth)
    created = []
    for index in range(7):
        response = client.post(
            "/api/subjects/manual",
            headers=headers,
            json={"name": f"Personal topic {index}"},
        )
        assert response.status_code == 200, response.text
        created.append(response.json()["id"])

    rejected = client.post(
        "/api/subjects/manual",
        headers=headers,
        json={"name": "One too many"},
    )
    assert rejected.status_code == 409
    assert "up to 8 subjects" in rejected.json()["detail"]
    assert len(client.get("/api/me/subjects", headers=headers).json()["subjects"]) == 8

    removed = client.delete(f"/api/subjects/{created[0]}/enroll", headers=headers)
    assert removed.status_code == 200
    freed_slot = client.post(
        "/api/subjects/manual",
        headers=headers,
        json={"name": "Slot reopened"},
    )
    assert freed_slot.status_code == 200, freed_slot.text
    mine = client.get("/api/me/subjects", headers=headers).json()["subjects"]
    assert len(mine) == 8
    assert any(subject["id"] == freed_slot.json()["id"] for subject in mine)


def test_manual_subject_automatically_builds_a_draft_path(
    client,
    database: sessionmaker[Session],
    user_factory,
    headers_factory,
    monkeypatch,
):
    import app.routes.discovery as discovery_routes

    class MockDiscovery:
        def search(self, query, level):
            if query == "Mathematics":
                return [], []
            assert query == "Computer networks"
            assert level == "middle_school"
            return [
                Candidate(
                    "Computer network",
                    "A system of interconnected computers.",
                    "Wikipedia",
                    "https://en.wikipedia.org/wiki/Computer_network",
                    0.96,
                )
            ], []

        def page_details(self, source_url):
            assert source_url == "https://en.wikipedia.org/wiki/Computer_network"
            return (
                "Computer network",
                "A system of interconnected computers.",
                ["Computer science"],
            )

        def section_details(self, title):
            assert title == "Computer network"
            return [
                {
                    "title": "Introduction",
                    "extract": (
                        "A computer network connects devices to share information and resources."
                    ),
                    "linked_terms": ["network", "computer"],
                    "link_count": 5,
                    "depth": 1,
                },
                {
                    "title": "Network architecture",
                    "extract": (
                        "Network architecture describes the structure of a computer network."
                    ),
                    "linked_terms": ["architecture", "network"],
                    "link_count": 4,
                    "depth": 2,
                },
            ]

    monkeypatch.setattr(discovery_routes, "_service", MockDiscovery())
    headers = headers_factory(user_factory("manual_auto_path_student"))
    response = client.post(
        "/api/subjects/manual",
        headers=headers,
        json={"name": "Computer networks"},
    )

    assert response.status_code == 200, response.text
    result = response.json()
    assert result["path_status"] == "built"
    assert result["topic_count"] == 2
    assert "Quiz questions are prepared when you open a topic" in result["message"]
    with database() as db:
        topics = db.query(Topic).filter_by(subject_id=result["id"]).order_by(Topic.order).all()
        assert [topic.name for topic in topics] == ["Introduction", "Network architecture"]
        assert all(topic.source_extract for topic in topics)
        subject = db.get(Subject, result["id"])
        assert subject is not None
        assert subject.source == "manual"
        assert subject.source_url == "https://en.wikipedia.org/wiki/Computer_network"


def test_manual_subject_offline_path_can_be_retried_with_clear_message(
    client,
    database: sessionmaker[Session],
    user_factory,
    headers_factory,
    monkeypatch,
):
    import app.routes.discovery as discovery_routes

    class OfflineDiscovery:
        def search(self, query, level):
            return [], ["Wikipedia is temporarily unavailable."]

    monkeypatch.setattr(discovery_routes, "_service", OfflineDiscovery())
    headers = headers_factory(user_factory("manual_offline_path_student"))
    response = client.post(
        "/api/subjects/manual",
        headers=headers,
        json={"name": "Computer networks"},
    )

    assert response.status_code == 200, response.text
    result = response.json()
    assert result["path_status"] == "offline"
    assert result["topic_count"] == 0
    assert "Search again or pick from results" in result["message"]
    retry = client.post(
        f"/api/subjects/{result['id']}/build-path",
        headers=headers,
    )
    assert retry.status_code == 200, retry.text
    assert retry.json()["path_status"] == "offline"
    with database() as db:
        enrollment = db.query(Enrollment).filter_by(subject_id=result["id"]).one()
        enrollment.diagnostic_completed = False
        db.commit()
    diagnostic = client.get(
        f"/api/subjects/{result['id']}/diagnostic",
        headers=headers,
    )
    assert diagnostic.status_code == 200, diagnostic.text
    assert diagnostic.json()["questions"] == []
    assert diagnostic.json()["session_id"] is None
    completed = client.post(
        f"/api/subjects/{result['id']}/diagnostic",
        headers=headers,
        json={"answers": {}},
    )
    assert completed.status_code == 200, completed.text
    assert completed.json()["progress"]["diagnostic_completed"] is True
    recommendations = client.get(
        f"/api/subjects/{result['id']}/recommendations",
        headers=headers,
    )
    assert recommendations.status_code == 200, recommendations.text
    assert recommendations.json()["recommendations"] == []
    progress = client.get(f"/api/subjects/{result['id']}/progress", headers=headers)
    assert progress.status_code == 200, progress.text
    assert progress.json()["topics"] == []
    history = client.get(f"/api/subjects/{result['id']}/history", headers=headers)
    assert history.status_code == 200, history.text
    assert history.json()["history"] == []
    improvement = client.get(f"/api/subjects/{result['id']}/improvement", headers=headers)
    assert improvement.status_code == 200, improvement.text
    assert improvement.json()["topics"] == []
    assert improvement.json()["message"] == "No topic-specific learning data yet."


def test_discovery_path_skips_limited_quizzes_and_isolates_subjects(
    client,
    database: sessionmaker[Session],
    user_factory,
    headers_factory,
    monkeypatch,
):
    import app.routes.discovery as discovery_routes

    class MockDiscovery:
        def search(self, query, level):
            if query.casefold() != "astronomy":
                return [], []
            return [
                Candidate(
                    "Foundations of Astronomy",
                    "A short astronomy overview.",
                    "Wikipedia",
                    "https://en.wikipedia.org/wiki/Astronomy",
                    0.95,
                )
            ], []

        def page_details(self, source_url):
            return (
                "Astronomy",
                "A public-source overview of astronomy.",
                ["Natural sciences"],
            )

        def section_details(self, title):
            return [
                {
                    "title": section,
                    "extract": "",
                    "linked_terms": [],
                    "link_count": 0,
                    "depth": 1,
                }
                for section in ["Observing the sky", "Planetary systems", "Stellar evolution"]
            ]

        def preview(self, candidate):
            return ["Observing the sky", "Planetary systems", "Stellar evolution"]

    monkeypatch.setattr(discovery_routes, "_service", MockDiscovery())
    monkeypatch.setattr(discovery_routes, "validate_provider_url", lambda _url: "en.wikipedia.org")

    auth = user_factory("discovery_student")
    headers = headers_factory(auth)
    search = client.get(
        "/api/discovery/search?q=astronomy&level=high_school",
        headers=headers,
    )
    assert search.status_code == 200
    candidate = search.json()["results"][0]
    preview = client.get(
        "/api/discovery/preview",
        headers=headers,
        params={
            "name": candidate["name"],
            "source_url": candidate["source_url"],
            "level": "high_school",
        },
    )
    assert preview.status_code == 200
    assert [topic["order"] for topic in preview.json()["topics"]] == [1, 2, 3]

    created = client.post(
        "/api/discovery/subjects",
        headers=headers,
        json={"name": candidate["name"], "source_url": candidate["source_url"]},
    )
    assert created.status_code == 200, created.text
    subject_id = created.json()["id"]
    assert created.json()["status"] == "draft"
    assert created.json()["label"] == "Draft / auto-built from public sources, unreviewed"
    assert created.json()["topic_count"] == 3
    assert any(
        subject["id"] == subject_id
        for subject in client.get("/api/me/subjects", headers=headers).json()["subjects"]
    )
    enrolled = client.post(
        f"/api/subjects/{subject_id}/enroll",
        headers=headers,
        json={"target_depth": "intermediate"},
    )
    assert enrolled.status_code == 200
    assert enrolled.json()["diagnostic_required"] is True
    with database() as db:
        topics = db.query(Topic).filter_by(subject_id=subject_id).order_by(Topic.order).all()
        assert [topic.name for topic in topics] == [
            "Observing the sky",
            "Planetary systems",
            "Stellar evolution",
        ]
        assert all(topic.source_url == candidate["source_url"] for topic in topics)
        assert db.query(TopicPrerequisite).filter_by(topic_id=topics[1].id).one()
        assert db.query(TopicPrerequisite).filter_by(topic_id=topics[2].id).one()
        assert db.query(Resource).filter_by(topic_id=topics[0].id).count() == 4
        user = db.query(User).filter_by(username="discovery_student").one()
        enrollment = db.get(Enrollment, (user.id, subject_id))
        assert enrollment.target_depth == "intermediate"
        assert enrollment.education_level_used == "middle_school"

    diagnostic = client.get(
        f"/api/subjects/{subject_id}/diagnostic",
        headers=headers,
    )
    assert diagnostic.status_code == 200
    assert diagnostic.json()["questions"] == []
    assert "limited quiz banks" in diagnostic.json()["message"]
    completed = client.post(
        f"/api/subjects/{subject_id}/diagnostic",
        headers=headers,
        json={"answers": {}, "self_ratings": {}, "session_id": diagnostic.json()["session_id"]},
    )
    assert completed.status_code == 200, completed.text
    assert completed.json()["feedback"] == []
    assert completed.json()["score_source"] == "graded quiz answers only"
    improvement = client.get(
        f"/api/subjects/{subject_id}/improvement",
        headers=headers,
    )
    assert improvement.status_code == 200
    assert improvement.json()["topics"] == []

    other_auth = user_factory("other_discovery_student")
    other_headers = headers_factory(other_auth)
    denied = client.post(
        f"/api/subjects/{subject_id}/enroll",
        headers=other_headers,
    )
    assert denied.status_code == 404


def test_manual_subject_can_be_enriched_in_place(
    client,
    user_factory,
    headers_factory,
    monkeypatch,
):
    import app.routes.discovery as discovery_routes

    class MockDiscovery:
        def search(self, query, level):
            return [], []

        def page_details(self, source_url):
            return ("A different provider title", "A short description.", [])

        def section_details(self, title):
            return [
                {
                    "title": "Core ideas",
                    "extract": "",
                    "linked_terms": [],
                    "link_count": 0,
                    "depth": 1,
                }
            ]

        def preview(self, candidate):
            return ["Core ideas"]

    monkeypatch.setattr(discovery_routes, "_service", MockDiscovery())
    monkeypatch.setattr(discovery_routes, "validate_provider_url", lambda _url: "en.wikipedia.org")
    headers = headers_factory(user_factory("manual_enrichment_student"))
    manual = client.post(
        "/api/subjects/manual",
        headers=headers,
        json={"name": "My own subject"},
    ).json()
    enriched = client.post(
        "/api/discovery/subjects",
        headers=headers,
        json={
            "name": "Astronomy",
            "source_url": "https://en.wikipedia.org/wiki/Astronomy",
            "manual_subject_id": manual["id"],
        },
    )
    assert enriched.status_code == 200, enriched.text
    assert enriched.json()["id"] == manual["id"]
    assert enriched.json()["name"] == "My own subject"
    assert enriched.json()["source"] == "manual"
    assert enriched.json()["topic_count"] == 1


def test_account_deletion_removes_owned_discovery_content(
    client,
    database: sessionmaker[Session],
    user_factory,
    headers_factory,
    monkeypatch,
):
    import app.routes.discovery as discovery_routes

    class MockDiscovery:
        def search(self, _query, _level):
            return [], []

        def page_details(self, source_url):
            return ("Private subject to delete", "A short overview.", [])

        def section_details(self, title):
            return [
                {
                    "title": heading,
                    "extract": "",
                    "linked_terms": [],
                    "link_count": 0,
                    "depth": 1,
                }
                for heading in ["Basics", "Advanced"]
            ]

        def preview(self, candidate):
            return ["Basics", "Advanced"]

    monkeypatch.setattr(discovery_routes, "_service", MockDiscovery())
    monkeypatch.setattr(discovery_routes, "validate_provider_url", lambda _url: "en.wikipedia.org")
    auth = user_factory("delete_discovery_student")
    headers = headers_factory(auth)
    created = client.post(
        "/api/discovery/subjects",
        headers=headers,
        json={
            "name": "Private subject to delete",
            "source_url": "https://en.wikipedia.org/wiki/Private_subject_to_delete",
        },
    )
    assert created.status_code == 200, created.text
    subject_id = created.json()["id"]
    with database() as db:
        user_id = db.query(User).filter_by(username="delete_discovery_student").one().id
    assert (
        client.request(
            "DELETE",
            "/api/account",
            headers=headers,
            json={"password": "Strong-Test-Pass1"},
        ).status_code
        == 200
    )
    with database() as db:
        assert db.get(Subject, subject_id) is None
        assert db.query(Topic).filter_by(subject_id=subject_id).count() == 0
        assert db.query(Resource).join(Topic).filter(Topic.subject_id == subject_id).count() == 0
        assert (
            db.query(TopicPrerequisite)
            .join(Topic, TopicPrerequisite.topic_id == Topic.id)
            .filter(Topic.subject_id == subject_id)
            .count()
            == 0
        )
        assert db.query(Enrollment).filter_by(user_id=user_id).count() == 0


def test_discovery_offline_and_ssrf_rejection(client, user_factory, headers_factory, monkeypatch):
    import app.routes.discovery as discovery_routes

    class OfflineDiscovery:
        def search(self, query, level):
            raise DiscoveryUnavailable("offline")

        def search_books(self, query):
            return [], ["Open Library is temporarily unavailable."]

    monkeypatch.setattr(discovery_routes, "_service", OfflineDiscovery())
    headers = headers_factory(user_factory("offline_discovery_student"))
    search = client.get("/api/discovery/search?q=biology", headers=headers)
    assert search.status_code == 200
    assert search.json()["results"] == []
    assert "temporarily offline" in search.json()["message"]
    books = client.get("/api/discovery/books?q=biology", headers=headers)
    assert books.status_code == 200
    assert books.json()["results"] == []
    assert books.json()["errors"]

    for url in (
        "http://en.wikipedia.org/wiki/Astronomy",
        "https://127.0.0.1/private",
        "https://en.wikipedia.org.evil.example/wiki/Astronomy",
        "https://user:pass@en.wikipedia.org/wiki/Astronomy",
    ):
        try:
            validate_provider_url(url)
        except ValueError:
            continue
        raise AssertionError(f"Unsafe provider URL was accepted: {url}")

    class PrivateDnsAnswer:
        def __getitem__(self, index):
            return ("10.0.0.2", 443)

    monkeypatch.setattr(
        "app.services.discovery.safety.socket.getaddrinfo",
        lambda *_args, **_kwargs: [(0, 0, 0, "", PrivateDnsAnswer())],
    )
    with pytest.raises(DiscoveryUnavailable, match="offline or unsafe"):
        _verify_public_dns("en.wikipedia.org")
