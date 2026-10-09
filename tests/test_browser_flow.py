from __future__ import annotations

import json
import os
import socket
import subprocess
import sys
import time
from pathlib import Path

import pytest
from playwright.sync_api import Page, expect
from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker

from app import models_db  # noqa: F401 - register ORM classes
from app.content.pack import import_content_pack
from app.database import Base
from app.models_db import Question, Resource, Subject, Topic, TopicPrerequisite, User
from app.services.subject_enrollment import enroll_user


@pytest.mark.browser
def test_register_quiz_history_logout_in_real_browser(page: Page, tmp_path: Path) -> None:
    db_path = tmp_path / "browser-flow.db"
    url = f"sqlite:///{db_path}"
    engine = create_engine(url, connect_args={"check_same_thread": False})

    @event.listens_for(engine, "connect")
    def _foreign_keys(connection, _record) -> None:
        connection.execute("PRAGMA foreign_keys=ON")

    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine)
    with factory() as db:
        for pack_name in ("mathematics", "physics"):
            pack_path = Path(__file__).resolve().parents[1] / "content" / "examples" / pack_name
            import_content_pack(pack_path, db)
    engine.dispose()

    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        port = sock.getsockname()[1]
    env = os.environ.copy()
    env.update(
        {
            "APP_ENV": "development",
            "DISCOVERY_OFFLINE": "1",
            "APP_SECRET": "playwright-browser-secret-with-at-least-32-characters",
            "DATABASE_URL": url,
            "ALLOWED_ORIGINS": f"http://127.0.0.1:{port}",
        }
    )
    server_log = (tmp_path / "uvicorn.log").open("w")
    server = subprocess.Popen(
        [
            sys.executable,
            "-m",
            "uvicorn",
            "app.main:app",
            "--host",
            "127.0.0.1",
            "--port",
            str(port),
        ],
        cwd=Path(__file__).resolve().parents[1],
        env=env,
        stdout=subprocess.DEVNULL,
        stderr=server_log,
    )
    errors: list[str] = []
    discovered_subject_id: list[str] = []

    def capture_console_error(message) -> None:
        if message.type == "error" and "favicon.ico" not in message.text.lower():
            errors.append(message.text)

    page.on("console", capture_console_error)
    page.on("pageerror", lambda error: errors.append(str(error)))
    try:
        base_url = f"http://127.0.0.1:{port}"
        deadline = time.monotonic() + 120
        while time.monotonic() < deadline:
            if server.poll() is not None:
                raise AssertionError("The test server exited before becoming ready")
            try:
                if page.request.get(f"{base_url}/health", timeout=500).ok:
                    break
            except Exception:
                time.sleep(0.2)
        else:
            raise AssertionError("The test server did not become ready")

        page.goto(base_url, wait_until="domcontentloaded")
        page.locator('.tab[data-tab="register"]').click()
        page.locator("#reg-user").fill("browser_learner")
        page.locator("#reg-pass").fill("Browser-Test-Password1")
        with page.expect_response(
            lambda response: response.url.endswith("/api/auth/register"),
            timeout=60_000,
        ) as registration_response:
            page.locator("#register-button").click()
        response = registration_response.value
        assert response.status == 200, response.text()
        expect(page.locator("#user-label")).to_contain_text("browser_learner", timeout=30_000)
        expect(page.locator("#onboarding-card")).to_be_visible(timeout=10_000)
        expect(page.locator("#privacy-notice")).to_contain_text("profile choices")
        page.locator("#profile-education-level").select_option("high_school")
        page.locator("#profile-institution-type").select_option("school")
        page.locator("#profile-grade-year").fill("Grade 10")
        page.locator("#profile-field").fill("Science")
        page.locator("#profile-goal").select_option("exam")
        page.locator("#profile-weekly-time").fill("5")
        page.locator("#profile-style").select_option("examples")
        page.locator("#profile-experience").select_option("some")
        page.locator("#profile-consent").check()
        page.locator("#save-profile-button").click()
        expect(page.locator("#subject-step")).to_be_visible(timeout=10_000)
        expect(page.locator("#subject-count")).to_have_text("0 of 8")
        page.locator("#include-sample-subjects").check()
        expect(page.locator("#onboarding-pack-select option")).to_have_count(3)
        page.locator("#onboarding-pack-select").select_option("mathematics")
        expect(page.locator("#add-pack-subject")).to_be_enabled()
        page.locator("#add-pack-subject").click()
        expect(page.locator("#subject-count")).to_have_text("1 of 8")
        expect(page.locator("#chosen-subjects")).to_contain_text("Mathematics")
        expect(page.locator("#onboarding-card h2:visible")).to_have_count(1)
        expect(page.get_by_role("heading", name="Choose your subjects")).to_have_count(1)
        expect(page.locator("#privacy-notice")).to_be_hidden()
        pack_options = page.locator("#onboarding-pack-select option")
        expect(pack_options).to_have_count(3)
        expect(
            page.locator('#onboarding-pack-select option[value="python-programming"]')
        ).to_have_text("Python Programming (not installed)")
        page.locator("#onboarding-pack-select").select_option("python-programming")
        page.locator("#add-pack-subject").click()
        expect(page.locator("#subject-step-message")).to_contain_text(
            "Python Programming", timeout=10_000
        )
        expect(page.locator("#subject-step-message")).to_contain_text(
            "Internet discovery is temporarily unavailable"
        )
        expect(page.locator("#subject-count")).to_have_text("2 of 8")
        expect(page.locator("#chosen-subjects")).to_contain_text("Python Programming")
        expect(page.get_by_role("button", name="Remove Python Programming")).to_be_visible()

        networking_fixture = json.loads(
            (Path(__file__).parent / "fixtures" / "computer_networking_sources.json").read_text()
        )
        source_url = networking_fixture["source_url"]

        def search_saved_source(route) -> None:
            route.fulfill(
                status=200,
                content_type="application/json",
                body=json.dumps(
                    {
                        "results": [
                            {
                                "name": "Computer networking",
                                "summary": (
                                    "A study of connected computer systems and data exchange."
                                ),
                                "source": "Wikipedia",
                                "source_url": source_url,
                                "confidence": 0.95,
                            }
                        ],
                        "errors": [],
                    }
                ),
            )

        def preview_saved_path(route) -> None:
            route.fulfill(
                status=200,
                content_type="application/json",
                body=json.dumps(
                    {
                        "topics": [
                            {"name": item["name"], "order": index + 1, "depth": "beginner"}
                            for index, item in enumerate(networking_fixture["topics"])
                        ],
                        "label": "Draft / auto-built from public sources, unreviewed",
                        "message": None,
                    }
                ),
            )

        def add_saved_subject(route) -> None:
            with factory() as db:
                user = db.query(User).filter_by(username="browser_learner").one()
                subject_id = f"web-computer-networking-{user.id}"
                discovered_subject_id.append(subject_id)
                subject = Subject(
                    id=subject_id,
                    name="Computer networking",
                    description="A test draft built from saved Wikipedia fixture material.",
                    questions_status="No quiz yet; draft curriculum requires teacher review",
                    source="discovered",
                    status="draft",
                    created_by=user.id,
                    source_url=source_url,
                )
                db.add(subject)
                db.flush()
                prerequisite_id = None
                for index, fixture_topic in enumerate(networking_fixture["topics"], start=1):
                    slug = f"{index}-{fixture_topic['name'].lower().replace(' ', '-')}"
                    topic_id = f"{subject_id}.{slug}"
                    topic = Topic(
                        id=topic_id,
                        subject_id=subject_id,
                        slug=slug,
                        name=fixture_topic["name"],
                        order=index,
                        source_url=source_url,
                        source_extract=fixture_topic["summary"],
                        provenance=json.dumps(
                            {
                                "provider": "Wikipedia",
                                "source_url": source_url,
                                "retrieved_at": "2026-10-11T00:00:00+00:00",
                                "linked_terms": fixture_topic["linked_terms"],
                                "wikidata_facts": [],
                            }
                        ),
                    )
                    db.add(topic)
                    db.flush()
                    if prerequisite_id:
                        db.add(
                            TopicPrerequisite(
                                topic_id=topic_id,
                                prerequisite_topic_id=prerequisite_id,
                            )
                        )
                    prerequisite_id = topic_id
                    db.add(
                        Resource(
                            id=f"{topic_id}.reference-1",
                            topic_id=topic_id,
                            type="article",
                            title=f"Wikipedia: {fixture_topic['name']}",
                            difficulty=float(index),
                            duration=15,
                            url=source_url,
                            source_url=source_url,
                        )
                    )
                    db.flush()
                enroll_user(db, user, subject, "beginner")
            route.fulfill(
                status=200,
                content_type="application/json",
                body=json.dumps(
                    {
                        "id": subject_id,
                        "name": "Computer networking",
                        "source": "discovered",
                        "status": "draft",
                        "label": "Draft / auto-built from public sources, unreviewed",
                        "topic_count": len(networking_fixture["topics"]),
                        "target_depth": "beginner",
                        "source_url": source_url,
                    }
                ),
            )

        page.route("**/api/discovery/search**", search_saved_source)
        page.route("**/api/discovery/preview**", preview_saved_path)
        page.route("**/api/discovery/subjects", add_saved_subject)
        page.locator("#discovery-query").fill("computer networking")
        page.locator("#search-subjects").click()
        result_card = page.locator("#discovery-results .discovery-result").first
        expect(result_card).to_be_visible(timeout=10_000)
        result_card.get_by_role("button", name="Preview topic path").click()
        expect(result_card.locator("ol")).to_contain_text("Computer network · beginner")
        result_card.get_by_role("button", name="Add subject").click()
        expect(page.locator("#subject-count")).to_have_text("3 of 8")
        expect(page.locator("#chosen-subjects")).to_contain_text("Computer networking")
        page.locator("#manual-subject-name").fill("Offline practice subject")
        page.locator("#add-manual-subject").click()
        expect(page.locator("#subject-step-message")).to_contain_text(
            "Internet discovery is temporarily unavailable"
        )
        expect(page.locator("#subject-count")).to_have_text("4 of 8")
        page.unroute("**/api/discovery/search**")
        page.unroute("**/api/discovery/preview**")
        page.unroute("**/api/discovery/subjects")
        page.locator("#finish-subject-step").click()
        expect(page.locator("#onboarding-card")).to_be_hidden(timeout=10_000)
        if not discovered_subject_id:
            raise AssertionError("The mocked discovered subject was not added")
        subject_id = discovered_subject_id[0]
        page.locator("#subject-select").select_option(subject_id)
        page.locator("#edit-profile-button").click()
        expect(page.locator("#profile-grade-year")).to_have_value("Grade 10")
        page.locator("#cancel-profile-edit").click()
        expect(page.locator("#start-diagnostic")).to_have_text("Start learning")
        token = page.evaluate("localStorage.getItem('token')")
        before_diagnostic = page.request.get(
            f"{base_url}/api/subjects/{subject_id}/progress",
            headers={"Authorization": "Bearer " + str(token)},
        ).json()
        page.locator("#start-diagnostic").click()
        expect(page.locator("#quiz-questions .question")).to_have_count(3, timeout=10_000)
        diagnostic_ids = page.locator("#quiz-questions .question").evaluate_all(
            "questions => questions.map(question => question.dataset.questionId)"
        )
        with factory() as db:
            correct_by_id = {
                question_id: db.get(Question, question_id).correct_option
                for question_id in diagnostic_ids
                if question_id is not None
            }
        for question_index in range(3):
            question_id = diagnostic_ids[question_index]
            if question_id is None:
                raise AssertionError("Diagnostic question is missing its content id")
            page.locator(f'input[name="q{question_index}"]').nth(correct_by_id[question_id]).check()
        page.evaluate(
            """() => {
              MASTERY_CHART.destroy();
              MASTERY_CHART = null;
              window.Chart = function() {
                throw new Error("Injected chart construction failure");
              };
            }"""
        )
        page.locator("#submit-activity").click()
        expect(page.locator("#modal-msg")).to_contain_text("Diagnostic complete", timeout=10_000)
        expect(page.locator("#diagnostic-card")).to_be_hidden(timeout=10_000)
        expect(page.locator("#chart-status")).to_contain_text("could not be displayed")
        expect(page.locator("#topic-map .topic-node")).to_have_count(3)
        after_diagnostic = page.request.get(
            f"{base_url}/api/subjects/{subject_id}/progress",
            headers={"Authorization": "Bearer " + str(token)},
        ).json()
        assert any(
            current["mastery"] != previous["mastery"]
            for current, previous in zip(
                after_diagnostic["topics"], before_diagnostic["topics"], strict=True
            )
        )
        recommendations = page.request.get(
            f"{base_url}/api/subjects/{subject_id}/recommendations",
            timeout=90_000,
            headers={"Authorization": f"Bearer {token}"},
        )
        assert recommendations.status == 200, recommendations.text()
        recommendation_items = recommendations.json()["recommendations"]
        assert recommendation_items, recommendations.text()
        expect(page.locator("#top-rec button[data-action]")).to_be_visible(timeout=10_000)
        alternatives = page.locator("#alt-recs li")
        if alternatives.count():
            expected_alternatives = recommendation_items[1:]
            assert alternatives.count() == len(expected_alternatives)
            for index, expected in enumerate(expected_alternatives):
                alternative = alternatives.nth(index)
                expect(alternative.locator("b")).to_have_text(expected["topic"])
                expect(alternative.locator("span")).to_contain_text(expected["resource_type"])
                expect(alternative.locator("span")).to_contain_text(
                    f"difficulty {float(expected['difficulty']):g}/5"
                )
                expect(alternative.get_by_role("button", name="Start")).to_be_visible()
        else:
            expect(page.locator("#alt-recs")).to_contain_text("No other topics are unlocked yet")

        page.reload(wait_until="networkidle")
        expect(page.locator("#app-view")).to_be_visible()
        expect(page.locator("#chart-status")).to_be_hidden()
        chart_height = page.locator("#mastery-chart").evaluate(
            "canvas => canvas.getBoundingClientRect().height"
        )
        assert chart_height < 400, f"Mastery chart height was {chart_height}px"
        if page.locator("#alt-recs li").count():
            expect(page.locator("#alt-recs li").first).to_be_visible()
        else:
            expect(page.locator("#alt-recs")).to_contain_text("No other topics are unlocked yet")

        page.route(
            "**/api/subjects/*/recommendations**",
            lambda route: route.fulfill(
                status=200,
                content_type="application/json",
                body=json.dumps({"recommendations": recommendation_items[:1]}),
            ),
        )
        page.reload(wait_until="networkidle")
        expect(page.locator("#alt-recs")).to_contain_text("No other topics are unlocked yet")
        page.unroute("**/api/subjects/*/recommendations**")
        page.reload(wait_until="networkidle")
        expect(page.locator("#top-rec button[data-action]")).to_be_visible()

        start_button = page.locator("#top-rec button[data-action]")
        expect(start_button).to_be_visible(timeout=30_000)
        start_button.click()
        expect(page.locator("#quiz-questions .question")).to_have_count(1, timeout=10_000)
        seen_question_ids: set[str] = set()
        for question_index in range(10):
            current_question_id = page.locator("#quiz-questions .question").get_attribute(
                "data-question-id"
            )
            if current_question_id is None or current_question_id in seen_question_ids:
                raise AssertionError("The adaptive quiz repeated or omitted a question")
            seen_question_ids.add(current_question_id)
            with factory() as db:
                current_question = db.get(Question, current_question_id)
                if current_question is None:
                    raise AssertionError("Generated question was not persisted")
                current_correct_option = current_question.correct_option
                source_sentence = current_question.source_sentence or current_question.explanation
            option_count = page.locator('input[name="q0"]').count()
            selected_option = (
                (current_correct_option + 1) % option_count
                if question_index == 0
                else current_correct_option
            )
            page.locator('input[name="q0"]').nth(selected_option).check()
            page.locator("#submit-activity").click()
            expect(page.locator("#quiz-questions .question-feedback")).to_contain_text(
                source_sentence, timeout=10_000
            )
            if question_index < 9:
                expect(page.locator("#quiz-questions .question")).to_have_count(1, timeout=10_000)
                next_question_id = page.locator("#quiz-questions .question").get_attribute(
                    "data-question-id"
                )
                assert next_question_id != current_question_id
            else:
                expect(page.locator("#quiz-questions .question")).to_have_count(0, timeout=10_000)
        assert len(seen_question_ids) == 10
        expect(page.locator("#history-table tbody tr")).to_have_count(
            len(seen_question_ids), timeout=15_000
        )
        expect(page.locator("#history-table tbody tr").first).to_contain_text("%")
        after_quiz = page.request.get(
            f"{base_url}/api/subjects/{subject_id}/progress",
            headers={"Authorization": "Bearer " + str(token)},
        ).json()
        assert any(topic["attempts"] > 0 for topic in after_quiz["topics"])
        assert any(
            current["mastery"] != previous["mastery"]
            for current, previous in zip(
                after_quiz["topics"], after_diagnostic["topics"], strict=True
            )
        )
        updated_recommendations = page.request.get(
            f"{base_url}/api/subjects/{subject_id}/recommendations",
            headers={"Authorization": "Bearer " + str(token)},
            timeout=90_000,
        )
        assert updated_recommendations.status == 200
        assert updated_recommendations.json()["recommendations"]
        page.locator("#cancel-activity").click()

        diagnostic_response = page.request.get(
            f"{base_url}/api/subjects/{discovered_subject_id[0]}/diagnostic",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert diagnostic_response.status == 200
        assert "correct_option" not in diagnostic_response.text()
        with factory() as db:
            learner = db.query(User).filter_by(username="browser_learner").one()
            empty_subject_id = f"manual-empty-path-{learner.id}"
            empty_subject = Subject(
                id=empty_subject_id,
                name="Empty subject",
                description="No topic path yet.",
                questions_status="No topic path yet",
                source="manual",
                status="draft",
                created_by=learner.id,
            )
            db.add(empty_subject)
            db.flush()
            enroll_user(db, learner, empty_subject)
            db.commit()

        page.reload(wait_until="networkidle")
        page.locator("#subject-select").select_option(empty_subject_id)
        expect(page.locator("#empty-path-recovery")).to_be_visible()
        expect(page.locator("#build-subject-path")).to_be_visible()
        expect(page.locator("#empty-path-message")).to_contain_text(
            "This subject has no topics yet"
        )
        expect(page.locator("#top-rec")).to_contain_text("How to start")

        page.route(
            f"**/api/subjects/{empty_subject_id}/build-path",
            lambda route: route.fulfill(
                status=200,
                content_type="application/json",
                body=json.dumps(
                    {
                        "id": empty_subject_id,
                        "name": "Empty subject",
                        "path_status": "offline",
                        "topic_count": 0,
                        "message": (
                            "Internet discovery is temporarily unavailable. "
                            "Search again or pick from results to build this path."
                        ),
                    }
                ),
            ),
        )
        page.locator("#build-subject-path").click()
        expect(page.locator("#empty-path-message")).to_contain_text(
            "Internet discovery is temporarily unavailable"
        )
        expect(page.locator("#retry-subject-discovery")).to_be_visible()
        expect(page.locator("#pick-discovery-results")).to_be_visible()
        page.unroute(f"**/api/subjects/{empty_subject_id}/build-path")

        page.locator("#logout-button").click()
        expect(page.locator("#auth-view")).to_be_visible()
        assert page.evaluate("localStorage.getItem('token')") is None
        assert not errors, f"Browser console errors (including CSP): {errors}"
    finally:
        server.terminate()
        try:
            server.wait(timeout=5)
        except subprocess.TimeoutExpired:
            server.kill()
            server.wait(timeout=5)
        server_log.close()
