from __future__ import annotations

import json
from collections import Counter
from itertools import groupby

import numpy as np
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session, sessionmaker

import app.services.recommender as recommender
from app.models_db import Question, StudentState, User
from app.routes.auth import limiter

TOPIC_IDS = [
    "mathematics.algebra",
    "mathematics.geometry",
    "mathematics.probability",
    "mathematics.calculus",
    "mathematics.statistics",
    "mathematics.linear-algebra",
]

PROFILES = {
    "new learner": dict(mastery=[0.25] * 6, ability=0.0, motivation=0.6, score=50.0),
    "weak in algebra": dict(
        mastery=[0.05, 0.5, 0.5, 0.5, 0.5, 0.5], ability=-0.3, motivation=0.6, score=45.0
    ),
    "strong everywhere": dict(mastery=[0.92] * 6, ability=1.0, motivation=0.8, score=90.0),
    "low motivation": dict(
        mastery=[0.35, 0.45, 0.4, 0.3, 0.5, 0.4], ability=-0.2, motivation=0.05, score=40.0
    ),
    "stuck on low scores": dict(
        mastery=[0.15, 0.2, 0.18, 0.22, 0.17, 0.19], ability=-1.2, motivation=0.3, score=25.0
    ),
    "near mastery": dict(
        mastery=[0.97, 0.94, 0.96, 0.95, 0.98, 0.93], ability=1.4, motivation=0.8, score=96.0
    ),
    "uneven learner": dict(
        mastery=[0.9, 0.15, 0.8, 0.2, 0.75, 0.1], ability=-0.1, motivation=0.5, score=55.0
    ),
    "mid-course learner": dict(
        mastery=[0.45, 0.55, 0.35, 0.6, 0.4, 0.5], ability=0.1, motivation=0.65, score=60.0
    ),
}


def _headers(auth: dict[str, str]) -> dict[str, str]:
    return {"Authorization": f"Bearer {auth['token']}"}


def _seed_profile(
    database: sessionmaker[Session],
    username: str,
    profile: dict[str, object],
) -> int:
    with database() as db:
        user = db.query(User).filter_by(username=username).one()
        state = db.query(StudentState).filter_by(user_id=user.id, subject_id="mathematics").one()
        state.mastery_est_json = json.dumps(dict(zip(TOPIC_IDS, profile["mastery"], strict=True)))
        state.attempts_json = json.dumps(dict.fromkeys(TOPIC_IDS, 0))
        state.recent_scores_json = json.dumps([profile["score"]] * 3)
        state.ability = float(profile["ability"])
        state.motivation = float(profile["motivation"])
        state.total_time_min = 0.0
        state.engagement_ma = 0.5
        state.last_difficulty = 3.0
        state.last_score = float(profile["score"])
        state.n_interactions = 0
        db.commit()
        return int(user.id)


def _answer_key(
    client: TestClient,
    database: sessionmaker[Session],
    headers: dict[str, str],
    action: int,
) -> list[int]:
    response = client.get(f"/api/quiz/{action}", headers=headers)
    assert response.status_code == 200, response.text
    with database() as db:
        answers = []
        for question in response.json()["questions"]:
            stored = db.get(Question, question["id"])
            assert stored is not None
            answers.append(stored.correct_option)
        return answers


def test_eight_profiles_30_api_submissions_and_fallback_comparison(
    client: TestClient,
    database: sessionmaker[Session],
    user_factory,
) -> None:
    original_assets = dict(recommender._ASSETS) if recommender._ASSETS is not None else None
    report: dict[str, object] = {}
    try:
        for index, (label, profile) in enumerate(PROFILES.items()):
            username = f"sanity_{index}"
            limiter.reset()
            auth = user_factory(username)
            user_id = _seed_profile(database, username, profile)
            headers = _headers(auth)
            catalog = client.get("/api/catalog", headers=headers).json()["catalog"]

            active = client.get("/api/recommend?top_k=5", headers=headers)
            assert active.status_code == 200, active.text
            active_initial = active.json()["recommendations"]
            active_assets = dict(recommender._ASSETS)
            recommender._ASSETS = {
                "predictor": None,
                "q_table": None,
                "mode": "zpd-fallback",
            }
            fallback = client.get("/api/recommend?top_k=5", headers=headers)
            recommender._ASSETS = active_assets
            assert fallback.status_code == 200, fallback.text
            fallback_initial = fallback.json()["recommendations"]
            overlap = len(
                {row["resource_id"] for row in active_initial}
                & {row["resource_id"] for row in fallback_initial}
            )

            selected_actions: list[int] = []
            recommendation_items: list[str] = []
            for _ in range(30):
                response = client.get("/api/recommend?top_k=5", headers=headers)
                assert response.status_code == 200, response.text
                choices = response.json()["recommendations"]
                assert 1 <= len(choices) <= 5
                recommendation_items.extend(item["resource_id"] for item in choices)
                action = int(choices[0]["action"])
                selected_actions.append(action)
                submitted = client.post(
                    "/api/interaction",
                    headers=headers,
                    json={
                        "action": action,
                        "answers": _answer_key(client, database, headers, action),
                        "duration": 1.0,
                    },
                )
                assert submitted.status_code == 200, submitted.text
                mastery = submitted.json()["state"]["mastery_est"]
                assert len(mastery) == len(TOPIC_IDS)
                assert all(0.0 <= float(value) <= 1.0 for value in mastery)

            history = client.get("/api/history?limit=200", headers=headers)
            assert history.status_code == 200
            assert len(history.json()["history"]) == 30
            with database() as db:
                final_state = (
                    db.query(StudentState)
                    .filter_by(user_id=user_id, subject_id="mathematics")
                    .one()
                )
                final_mastery = final_state.mastery_est
            action_counts = Counter(selected_actions)
            topics_seen = sorted({catalog[action]["topic"] for action in selected_actions})
            consecutive_repeat = max(
                (len(list(group)) for _, group in groupby(selected_actions)), default=0
            )
            final_values = [float(final_mastery.get(topic_id, 0.25)) for topic_id in TOPIC_IDS]
            report[label] = {
                "active_top5": [
                    {
                        "topic": item["topic"],
                        "resource_type": item["resource_type"],
                        "difficulty": item["difficulty"],
                    }
                    for item in active_initial
                ],
                "fallback_top5": [
                    {
                        "topic": item["topic"],
                        "resource_type": item["resource_type"],
                        "difficulty": item["difficulty"],
                    }
                    for item in fallback_initial
                ],
                "active_fallback_overlap": overlap,
                "topics_seen_in_30": topics_seen,
                "distinct_actions_in_30": len(action_counts),
                "largest_consecutive_same_action_run": consecutive_repeat,
                "selected_action_repeat_fraction": round(
                    1.0 - len(action_counts) / len(selected_actions), 4
                ),
                "recommendation_item_repeat_fraction": round(
                    1.0 - len(set(recommendation_items)) / len(recommendation_items), 4
                ),
                "mastery_start": profile["mastery"],
                "mastery_end": [round(value, 4) for value in final_values],
                "mastery_min": round(float(np.min(final_values)), 4),
                "mastery_max": round(float(np.max(final_values)), 4),
            }
    finally:
        recommender._ASSETS = original_assets

    print("RECOMMENDATION_SANITY_JSON=" + json.dumps(report, sort_keys=True))
