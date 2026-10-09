from __future__ import annotations

import random
from pathlib import Path

import numpy as np
import pytest

from app.services import recommender
from app.services.learning import apply_interaction
from app.services.numpy_predictor import NumpyPredictor
from app.services.quiz import grade_answers, public_questions
from src.domain import get_domain, get_training_domains
from src.env import LearningEnv
from src.feature_schema import RAW_FEATURES, build_candidate_features, build_design_matrix
from src.utils import gini, set_seed


def _profile() -> dict:
    return {
        "mastery_est": [0.25] * 6,
        "attempts": [0] * 6,
        "recent_scores": [],
        "total_time_min": 0.0,
        "engagement_ma": 0.5,
        "last_difficulty": 3.0,
        "last_score": 50.0,
        "n_interactions": 0,
        "ability": 0.0,
        "motivation": 0.6,
    }


def test_learning_updates_keep_mastery_and_engagement_in_range() -> None:
    catalog, _ = get_domain()
    profile = _profile()
    for score, duration in ((0.0, 0.5), (100.0, 120.0), (65.0, 20.0)):
        outcome = apply_interaction(profile, 0, catalog, score, duration)
        mastery = profile["mastery_est"][catalog[0]["topic"]]
        assert 0.0 <= mastery <= 1.0
        assert 0.0 <= profile["engagement_ma"] <= 1.0
        assert 0.0 <= outcome["engagement"] <= 1.0
    assert profile["n_interactions"] == 3


def test_domain_catalog_has_thirty_resources() -> None:
    catalog, _ = get_domain()
    assert len(catalog) == 30


def test_simulator_varies_learner_level_and_goal_as_model_features() -> None:
    domains = get_training_domains(seed=83)
    learner_levels = {
        student["learner_level"] for _catalog, students, _topics in domains for student in students
    }
    goals = {
        student["learning_goal"] for _catalog, students, _topics in domains for student in students
    }
    assert min(learner_levels) < 20
    assert max(learner_levels) > 80
    assert goals == {"exam", "skill", "career", "curiosity"}

    catalog, students, topics = domains[0]
    env = LearningEnv(catalog, students, topics=topics, seed=83)
    features = env.candidate_features()
    assert {"learner_level", "learning_goal"} <= set(RAW_FEATURES)
    assert {"learner_level", "learning_goal"} <= set(features.columns)
    assert "learner_level" in build_design_matrix(features).columns
    assert "goal_exam" in build_design_matrix(features).columns


def test_random_helpers_are_reproducible_from_seed() -> None:
    set_seed(731)
    first = (random.random(), np.random.random())
    set_seed(731)
    second = (random.random(), np.random.random())
    assert first == second


def test_gini_known_values() -> None:
    assert gini([0, 0, 10, 10]) == 0.5
    assert gini([1, 1, 1]) == 0.0
    assert gini([]) == 0.0


def test_quiz_public_view_hides_key_and_grading_rejects_bad_answers() -> None:
    public = public_questions("Algebra")
    assert len(public) == 3
    assert all("answer" not in question for question in public)
    assert grade_answers("Algebra", [1, 0, 1])["score"] == 100.0
    for topic, answers in (("Unknown", []), ("Algebra", [1]), ("Algebra", [1, 0, 99])):
        with pytest.raises(ValueError):
            grade_answers(topic, answers)
    with pytest.raises(ValueError):
        public_questions("Unknown")


def test_recommender_loads_saved_artifacts_when_available() -> None:
    recommender._ASSETS = None
    mode = recommender.get_mode()
    assert mode in {"hybrid", "zpd-fallback"}
    catalog, _ = get_domain()
    profile = {
        **_profile(),
        "mastery_est": {item["topic_id"]: 0.25 for item in catalog},
        "attempts": {item["topic_id"]: 0 for item in catalog},
    }
    prerequisites = {item["topic_id"]: item["prerequisites"] for item in catalog}
    recommendations = recommender.recommend_for(profile, catalog, prerequisites, top_k=3)
    assert 1 <= len(recommendations) <= 3
    assert all("resource_id" in rec and "topic" in rec for rec in recommendations)


def test_numpy_serving_export_matches_tensorflow_predictions() -> None:
    pytest.importorskip("tensorflow")
    from src.task3_model import ScorePredictor

    predictor_dir = Path(recommender.PREDICTOR_DIR)
    tensorflow_predictor = ScorePredictor.load(str(predictor_dir))
    numpy_predictor = NumpyPredictor.load(predictor_dir)
    catalog, _ = get_domain()
    profile = {
        "mastery_est": {item["topic_id"]: 0.25 for item in catalog},
        "attempts": {item["topic_id"]: 0 for item in catalog},
        "recent_scores": [43.0, 72.0],
        "total_time_min": 25.0,
        "engagement_ma": 0.6,
        "learner_level": 40.0,
        "learning_goal": "exam",
    }
    prerequisites = {item["topic_id"]: item["prerequisites"] for item in catalog}

    features = build_candidate_features(profile, catalog, prerequisites)
    tensorflow_predictions = tensorflow_predictor.predict(features)
    numpy_predictions = numpy_predictor.predict(features)
    np.testing.assert_allclose(numpy_predictions, tensorflow_predictions, rtol=1e-5, atol=1e-4)


def test_recommender_uses_zpd_when_artifacts_are_missing(tmp_path, monkeypatch) -> None:
    recommender._ASSETS = None
    monkeypatch.setattr(recommender, "PREDICTOR_DIR", str(tmp_path / "no-predictor"))
    monkeypatch.setattr(recommender, "Q_TABLE_PATH", str(tmp_path / "no-q-table.json"))
    catalog, _ = get_domain()
    profile = {
        **_profile(),
        "mastery_est": {item["topic_id"]: 0.25 for item in catalog},
        "attempts": {item["topic_id"]: 0 for item in catalog},
    }
    prerequisites = {item["topic_id"]: item["prerequisites"] for item in catalog}
    recommendations = recommender.recommend_for(profile, catalog, prerequisites, top_k=4)
    assert recommender.get_mode() == "zpd-fallback"
    assert 1 <= len(recommendations) <= 4
    recommender._ASSETS = None


def test_recommender_avoids_immediate_resource_repeats_and_covers_other_topics() -> None:
    recommender._ASSETS = {"predictor": None, "q_table": None, "mode": "zpd-fallback"}
    catalog, _ = get_domain()
    profile = {
        **_profile(),
        "mastery_est": {item["topic_id"]: 0.25 for item in catalog},
        "attempts": {item["topic_id"]: 0 for item in catalog},
    }
    prerequisites = {item["topic_id"]: item["prerequisites"] for item in catalog}
    previous = catalog[0]

    recommendations = recommender.recommend_for(
        profile,
        catalog,
        prerequisites,
        top_k=5,
        recent_history=[{"resource_id": previous["resource_id"], "topic_id": previous["topic_id"]}],
    )

    assert recommendations
    assert recommendations[0]["resource_id"] != previous["resource_id"]
    assert all("recency_penalty" in row["explanation"] for row in recommendations)
    assert all("topic_coverage_bonus" in row["explanation"] for row in recommendations)
    recommender._ASSETS = None
