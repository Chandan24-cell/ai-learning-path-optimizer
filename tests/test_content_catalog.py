from __future__ import annotations

from sqlalchemy.orm import Session, sessionmaker

from app.models_db import Question, Resource, Subject, Topic, TopicPrerequisite


def test_subject_catalog_lists_valid_packs_and_surfaces_invalid_pack_errors(
    client,
    monkeypatch,
    tmp_path,
):
    import app.content.catalog as catalog

    (tmp_path / "broken-pack").mkdir()
    (tmp_path / "broken-pack" / "content.json").write_text("{", encoding="utf-8")
    monkeypatch.setattr(catalog, "CONTENT_ROOT", tmp_path)

    response = client.get("/api/subjects?include_samples=true")
    assert response.status_code == 200
    payload = response.json()
    assert {pack["id"] for pack in payload["subjects"]} == {
        "mathematics",
        "physics",
        "python-programming",
    }
    assert payload["errors"][0]["directory"] == "broken-pack"
    assert "invalid content pack" in payload["errors"][0]["message"]


def test_subject_catalog_lists_all_packs_and_installs_on_demand(
    client,
    database: sessionmaker[Session],
    user_factory,
    headers_factory,
):
    auth = user_factory("pack_catalog_student")
    headers = headers_factory(auth)

    response = client.get("/api/subjects?include_samples=true")
    assert response.status_code == 200, response.text
    catalog = response.json()
    assert {pack["id"] for pack in catalog["subjects"]} == {
        "mathematics",
        "physics",
        "python-programming",
    }
    assert all(pack["installed"] for pack in catalog["subjects"])
    assert catalog["errors"] == []

    with database() as db:
        topic_ids = [
            topic.id for topic in db.query(Topic).filter_by(subject_id="python-programming")
        ]
        db.query(TopicPrerequisite).filter(
            TopicPrerequisite.topic_id.in_(topic_ids)
            | TopicPrerequisite.prerequisite_topic_id.in_(topic_ids)
        ).delete(synchronize_session=False)
        db.query(Question).filter(Question.topic_id.in_(topic_ids)).delete(
            synchronize_session=False
        )
        db.query(Resource).filter(Resource.topic_id.in_(topic_ids)).delete(
            synchronize_session=False
        )
        db.query(Topic).filter_by(subject_id="python-programming").delete(synchronize_session=False)
        db.delete(db.get(Subject, "python-programming"))
        db.commit()

    response = client.get("/api/subjects?include_samples=true")
    python_pack = next(
        pack for pack in response.json()["subjects"] if pack["id"] == "python-programming"
    )
    assert python_pack["installed"] is False

    installed = client.post(
        "/api/subjects/python-programming/install",
        headers=headers,
        json={"target_depth": "intermediate"},
    )
    assert installed.status_code == 200, installed.text
    assert installed.json()["installed"] is True
    assert installed.json()["diagnostic_required"] is True
    assert installed.json()["topics"] == 6

    repeated = client.post(
        "/api/subjects/python-programming/install",
        headers=headers,
        json={"target_depth": "intermediate"},
    )
    assert repeated.status_code == 200, repeated.text
    assert (
        len(
            [
                subject
                for subject in client.get("/api/me/subjects", headers=headers).json()["subjects"]
                if subject["id"] == "python-programming"
            ]
        )
        == 1
    )
    assert (
        next(
            pack
            for pack in client.get("/api/subjects?include_samples=true").json()["subjects"]
            if pack["id"] == "python-programming"
        )["installed"]
        is True
    )


def test_samples_are_hidden_by_default_and_available_explicitly(client, user_factory):
    user_factory("sample_visibility_student")
    default_catalog = client.get("/api/subjects").json()["subjects"]
    sample_catalog = client.get("/api/subjects?include_samples=true").json()["subjects"]
    assert not {"mathematics", "physics", "python-programming"} & {
        item["id"] for item in default_catalog
    }
    assert {"mathematics", "physics", "python-programming"} <= {
        item["id"] for item in sample_catalog
    }


def test_registration_does_not_pre_enroll_a_sample_subject(client):
    registered = client.post(
        "/api/auth/register",
        json={"username": "empty_start_student", "password": "Strong-Test-Pass1"},
    )
    assert registered.status_code == 200, registered.text
    headers = {"Authorization": f"Bearer {registered.json()['token']}"}
    profile = client.put(
        "/api/me/profile",
        headers=headers,
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
    assert profile.status_code == 200, profile.text
    assert client.get("/api/me/subjects", headers=headers).json()["subjects"] == []
    assert client.get("/api/me/state", headers=headers).status_code == 409


def test_install_pack_rejects_invalid_pack_clearly(
    client,
    user_factory,
    headers_factory,
    monkeypatch,
    tmp_path,
):
    import app.content.catalog as catalog

    pack_dir = tmp_path / "broken-pack"
    pack_dir.mkdir()
    (pack_dir / "content.json").write_text("{", encoding="utf-8")
    monkeypatch.setattr(catalog, "CONTENT_ROOT", tmp_path)
    auth = user_factory("invalid_pack_student")
    response = client.post(
        "/api/subjects/broken-pack/install",
        headers=headers_factory(auth),
    )
    assert response.status_code == 422
    assert "failed validation" in response.json()["detail"]
