from __future__ import annotations

import json
from pathlib import Path

from app.models_db import Question, QuestionSession, Subject, Topic, User
from app.services.questions.adaptive import public_adaptive_question, select_question
from app.services.questions.rule_based import (
    RuleBasedQuestionGenerator,
    adaptive_difficulty,
    answer_is_masked,
    limited_quiz,
    options_pass_quality,
    sentence_passes_quality,
)
from app.services.questions.store import ensure_topic_question_bank

FIXTURE = Path(__file__).parent / "fixtures" / "question_sources.json"


def _fixture() -> dict:
    return json.loads(FIXTURE.read_text(encoding="utf-8"))


def test_rule_generator_builds_cited_question_types_from_saved_source() -> None:
    material = _fixture()
    questions = RuleBasedQuestionGenerator().generate_questions(
        "Python",
        material["topic"],
        source_extract=material["summary"],
        source_url=material["source_url"],
        linked_terms=material["linked_terms"],
        sibling_terms=material["sibling_terms"],
        sibling_topics=material["sibling_topics"],
        wikidata_facts=material["wikidata_facts"],
        sibling_facts=material["sibling_facts"],
        topic_order=2,
        topic_count=8,
        learner_level=70,
    )
    types = {question["question_type"] for question in questions}
    assert {"definition_to_term", "cloze", "true_false", "wikidata_fact"} <= types
    for question in questions:
        assert question["source_url"] == material["source_url"]
        assert question["status"].endswith("unreviewed")
        assert question["explanation"]
        assert "correct_option" in question
        assert answer_is_masked(question["options"][question["correct_option"]], question["text"])


def test_sentence_and_option_quality_filters_reject_unusable_content() -> None:
    assert not sentence_passes_quality(
        "It is a sentence with enough words to fail pronoun filtering."
    )
    assert not sentence_passes_quality(
        "This is a sentence with enough words but starts with an unresolved pronoun."
    )
    assert not sentence_passes_quality(
        "Python has a useful runtime model for many kinds of programs [1]."
    )
    assert not sentence_passes_quality(
        "Python has a useful runtime model (with extra detail) for many kinds of programs."
    )
    assert not sentence_passes_quality("Python is cool.")
    assert not options_pass_quality(["Python", "Ruby"], 0, "The answer is hidden here.")
    assert not options_pass_quality(
        ["Python", "Python", "Ruby", "Racket"], 0, "The answer is hidden here."
    )
    assert not options_pass_quality(
        ["Python", "R", "Ruby", "Kotlin"], 0, "The answer is hidden here."
    )
    assert not answer_is_masked("Python", "Python is the answer.")


def test_question_generator_rejects_short_or_unsupported_source() -> None:
    generator = RuleBasedQuestionGenerator()
    assert generator.generate_questions("Python", "Python", source_url="https://example.com") == []
    questions = generator.generate_questions(
        "Python",
        "Python",
        source_extract="It is a short sentence with enough words to trigger a pronoun filter.",
        source_url="https://en.wikipedia.org/wiki/Python_(programming_language)",
        sibling_topics=["Racket", "Groovy", "Kotlin"],
    )
    assert questions == []
    assert (
        generator.generate_questions(
            "Python",
            "Python",
            source_extract="Python is a subject that uses enough valid words for quality checks.",
            source_url="https://example.com/Python",
            sibling_topics=["Racket", "Groovy", "Kotlin"],
        )
        == []
    )


def test_wikidata_extracts_keep_wikidata_attribution() -> None:
    question = RuleBasedQuestionGenerator().generate_questions(
        "Wikidata",
        "Wikidata",
        source_extract=(
            "Wikidata is a knowledge base that stores structured records about topics."
        ),
        source_url="https://www.wikidata.org/wiki/Q2013",
        sibling_topics=["Wikipedia", "OpenStreetMap", "DBpedia"],
    )
    assert question
    assert all(item["attribution"] == "Wikidata, CC0" for item in question)


def test_quality_filters_reject_overlong_odd_and_mismatched_fact_options() -> None:
    overlong = "Python is " + " ".join(f"word{index}" for index in range(29)) + "."
    assert not sentence_passes_quality(overlong)
    assert not sentence_passes_quality(
        "Python offers useful tools for students learning programming @ runtime."
    )
    assert not options_pass_quality(
        ["1991", "2001", "2011", "2021"],
        0,
        "Which year did the source record?",
        fact_type="entity",
    )
    assert not options_pass_quality(
        ["Python", "Ruby", "Racket", "1991"],
        0,
        "Which programming language is referenced here?",
    )


def test_question_difficulty_tracks_level_position_and_recent_answers() -> None:
    struggling = adaptive_difficulty(
        2.0, topic_order=1, topic_count=8, learner_level=10, mastery=0.1, previous_correct=False
    )
    progressing = adaptive_difficulty(
        2.0, topic_order=8, topic_count=8, learner_level=90, mastery=0.9, previous_correct=True
    )
    assert progressing > struggling
    assert limited_quiz(4)
    assert not limited_quiz(5)


def test_question_banks_are_generated_lazily_cached_and_marked_limited(database) -> None:
    with database() as db:
        subject = Subject(id="stored-source", name="Stored Source", description="")
        db.add(subject)
        db.flush()
        topic = Topic(
            id="stored-source.python",
            subject_id=subject.id,
            slug="python",
            name="Python",
            order=1,
            source_url="https://en.wikipedia.org/wiki/Python_(programming_language)",
            source_extract=(
                "Python is an interpreted, high-level, general-purpose programming language "
                "with dynamic semantics. Python supports multiple programming paradigms and "
                "uses a comprehensive standard library for many tasks."
            ),
            provenance=json.dumps(
                {
                    "provider": "Wikipedia",
                    "linked_terms": [
                        "dynamic semantics",
                        "programming paradigms",
                        "standard library",
                        "static semantics",
                        "dynamic typing",
                        "type inference",
                    ],
                }
            ),
        )
        db.add(topic)
        db.add_all(
            [
                Topic(
                    id=f"stored-source.{sibling.casefold()}",
                    subject_id=subject.id,
                    slug=sibling.casefold(),
                    name=sibling,
                    order=index,
                )
                for index, sibling in enumerate(["Racket", "Groovy", "Kotlin"], start=2)
            ]
        )
        db.flush()

        first_bank = ensure_topic_question_bank(db, topic, 60)
        db.flush()
        cached_bank = ensure_topic_question_bank(db, topic, 60)
        assert first_bank
        assert [question.id for question in cached_bank] == [question.id for question in first_bank]
        assert all(question.source_url == topic.source_url for question in cached_bank)
        assert topic.quiz_status in {"ready", "limited"}
        definition = next(
            question for question in cached_bank if question.question_type == "definition_to_term"
        )
        assert set(definition.options) == {"Python", "Racket", "Groovy", "Kotlin"}

        empty_topic = Topic(
            id="stored-source.empty",
            subject_id=subject.id,
            slug="empty",
            name="Empty",
            order=2,
        )
        db.add(empty_topic)
        db.flush()
        assert ensure_topic_question_bank(db, empty_topic, 60) == []
        assert empty_topic.quiz_status == "limited"
        assert ensure_topic_question_bank(db, empty_topic, 60) == []


def test_adaptive_selection_prefers_unseen_and_reuses_only_after_bank_exhaustion(database) -> None:
    with database() as db:
        user = User(username="question-selector", hashed_password="test-hash", role="student")
        subject = Subject(id="selector-subject", name="Selector Subject", description="")
        db.add_all([user, subject])
        db.flush()
        topic = Topic(
            id="selector-subject.basics",
            subject_id=subject.id,
            slug="basics",
            name="Basics",
            order=1,
        )
        db.add(topic)
        db.flush()
        questions = [
            Question(
                id=f"selector-subject.basics.q{index}",
                topic_id=topic.id,
                difficulty=float(index),
                text=f"Question {index}",
                options_json='["First", "Second"]',
                correct_option=0,
                explanation="Explanation",
            )
            for index in range(1, 3)
        ]
        db.add_all(questions)
        db.flush()
        first_session = QuestionSession(
            id="selector-session-one",
            user_id=user.id,
            subject_id=subject.id,
            topic_id=topic.id,
            resource_id="resource",
            mode="activity",
            max_questions=5,
            asked_count=0,
            correct_count=0,
        )
        db.add(first_session)
        db.flush()
        selected_first = select_question(
            db,
            user_id=user.id,
            subject_id=subject.id,
            session=first_session,
            topic=topic,
            questions=questions,
            learner_level=50,
            mastery=0.5,
            previous_correct=None,
            topic_count=1,
        )
        assert selected_first is not None
        db.flush()
        public = public_adaptive_question(selected_first)
        assert "correct_option" not in public
        selected_second = select_question(
            db,
            user_id=user.id,
            subject_id=subject.id,
            session=first_session,
            topic=topic,
            questions=questions,
            learner_level=50,
            mastery=0.5,
            previous_correct=True,
            topic_count=1,
        )
        assert selected_second is not None
        db.flush()
        assert selected_second.question.id != selected_first.question.id

        next_session = QuestionSession(
            id="selector-session-two",
            user_id=user.id,
            subject_id=subject.id,
            topic_id=topic.id,
            resource_id="resource",
            mode="activity",
            max_questions=5,
            asked_count=0,
            correct_count=0,
        )
        db.add(next_session)
        db.flush()
        reused = select_question(
            db,
            user_id=user.id,
            subject_id=subject.id,
            session=next_session,
            topic=topic,
            questions=questions,
            learner_level=50,
            mastery=0.5,
            previous_correct=None,
            topic_count=1,
        )
        assert reused is not None
        assert reused.reused
        assert next_session.reused_questions
        assert (
            select_question(
                db,
                user_id=user.id,
                subject_id=subject.id,
                session=next_session,
                topic=topic,
                questions=[],
                learner_level=50,
                mastery=0.5,
                previous_correct=None,
                topic_count=1,
            )
            is None
        )
