"""Subject-agnostic recommendation ranking and prerequisite-aware fallback."""

from __future__ import annotations

import os
import threading
from collections.abc import Mapping, Sequence
from pickle import UnpicklingError  # nosec B403: used only to catch trusted joblib load errors.
from typing import Any, Protocol, TypedDict, cast

import numpy as np

from app.config import settings
from app.services.numpy_predictor import NumpyPredictor
from src.config import RESOURCE_TYPES
from src.domain import zpd_factor
from src.feature_schema import (
    LEARNING_GOALS,
    PREREQUISITE_THRESHOLD,
    RAW_FEATURES,
    build_candidate_features,
    coverage_value,
    feature_row,
    q_action,
    q_state,
)
from src.q_table import load_q_table

_LOCK = threading.Lock()


class Predictor(Protocol):
    pipeline: object

    def predict(self, df: Any) -> np.ndarray: ...


QTable = dict[tuple[int, ...], np.ndarray]


class ModelAssets(TypedDict):
    predictor: Predictor | None
    q_table: QTable | None
    mode: str


_ASSETS: ModelAssets | None = None
Q_TABLE_PATH = os.path.join(str(settings.model_dir), "q_table.json")
PREDICTOR_DIR = os.path.join(str(settings.model_dir), "predictor")
_ENGAGEMENT_PRIORS = {
    "video": 0.70,
    "article": 0.45,
    "quiz": 0.55,
    "interactive": 0.85,
    "project": 0.90,
}


def _load_predictor() -> Predictor | None:
    try:
        predictor = cast(Predictor, NumpyPredictor.load(PREDICTOR_DIR))
        pipeline = predictor.pipeline
        fitted_columns = set(getattr(pipeline, "columns_after_corr_", ()))
        expected_columns = (
            {
                feature
                for feature in RAW_FEATURES
                if feature not in {"resource_type", "learning_goal"}
            }
            | {"log_attempts", "log_time"}
            | {f"rtype_{resource_type}" for resource_type in RESOURCE_TYPES}
            | {f"goal_{goal}" for goal in LEARNING_GOALS}
        )
        if not expected_columns.issubset(fitted_columns):
            raise ValueError(
                "predictor feature schema does not match the current candidate features"
            )
        return predictor
    except (
        OSError,
        ValueError,
        KeyError,
        ImportError,
        AttributeError,
        TypeError,
        UnpicklingError,
    ) as exc:
        print(f"[recommender] predictor unavailable ({type(exc).__name__}); using fallback.")
        return None


def _load_q_table() -> QTable | None:
    try:
        return cast(QTable, load_q_table(Q_TABLE_PATH))
    except (OSError, ValueError) as exc:
        print(f"[recommender] Q-table unavailable ({type(exc).__name__}); using fallback.")
        return None


def _load_assets() -> ModelAssets:
    global _ASSETS
    if _ASSETS is not None:
        return _ASSETS
    with _LOCK:
        if _ASSETS is None:
            predictor = _load_predictor()
            q_table = _load_q_table()
            hybrid = predictor is not None and q_table is not None
            _ASSETS = {
                "predictor": predictor,
                "q_table": q_table,
                "mode": "hybrid" if hybrid else "zpd-fallback",
            }
            print(f"[recommender] loaded in mode = {_ASSETS['mode']}")
        assets = _ASSETS
    if assets is None:
        raise RuntimeError("Recommender assets failed to initialize")
    return assets


def _ready(
    candidate: Mapping,
    profile: Mapping,
    prerequisites: Mapping[str, Sequence[str]],
) -> bool:
    prerequisite_ids = prerequisites.get(str(candidate["topic_id"]), ())
    mastery = profile.get("mastery_est", {})
    return all(
        float(mastery.get(prerequisite_id, 0.25)) >= PREREQUISITE_THRESHOLD
        for prerequisite_id in prerequisite_ids
    )


def recommend_for(
    profile: Mapping,
    catalog: Sequence[Mapping],
    prerequisites: Mapping[str, Sequence[str]],
    top_k: int = 5,
    recent_history: Sequence[Mapping] = (),
) -> list[dict]:
    """Rank available subject resources without encoding topic identity."""
    if top_k < 1:
        return []
    eligible = [item for item in catalog if _ready(item, profile, prerequisites)]
    if not eligible:
        return []
    recent_history = recent_history[:12]
    most_recent_resource = next(
        (str(row["resource_id"]) for row in recent_history if row.get("resource_id")), None
    )
    if most_recent_resource is not None:
        without_last_resource = [
            item
            for item in eligible
            if str(item.get("id", item.get("resource_id"))) != most_recent_resource
        ]
        if without_last_resource:
            eligible = without_last_resource

    rows = [
        feature_row(profile, item, prerequisites.get(str(item["topic_id"]), ()))
        for item in eligible
    ]
    features = build_candidate_features(profile, eligible, prerequisites)
    assets = _load_assets()
    predictor = assets["predictor"]
    q_table = assets["q_table"]

    if predictor is not None:
        predicted = np.asarray(predictor.predict(features), dtype=float) / 100.0
    else:
        predicted = np.asarray(
            [
                0.35
                + 0.45 * float(row["candidate_topic_mastery"])
                + 0.20 * float(row["prerequisite_mastery_average"])
                - 0.05 * abs(float(row["difficulty_gap"]))
                for row in rows
            ],
            dtype=float,
        )
    predicted = np.clip(predicted, 0.0, 1.0)

    q_values = np.full(len(eligible), 0.5, dtype=float)
    if q_table is not None:
        for index, row in enumerate(rows):
            values = q_table.get(q_state(row, True))
            if values is not None:
                q_values[index] = float(values[q_action(row)])
        low, high = float(q_values.min()), float(q_values.max())
        q_values = (q_values - low) / (high - low) if high > low else np.full_like(q_values, 0.5)

    engagement = np.asarray(
        [
            0.5 * float(row["engagement"]) + 0.5 * _ENGAGEMENT_PRIORS[str(row["resource_type"])]
            for row in rows
        ],
        dtype=float,
    )
    difficulty_fit = np.asarray(
        [
            zpd_factor(
                float(row["candidate_topic_mastery"]),
                float(candidate["difficulty"]),
            )
            for candidate, row in zip(eligible, rows, strict=True)
        ],
        dtype=float,
    )
    coverage = np.asarray([coverage_value(row) for row in rows], dtype=float)
    if predictor is None or q_table is None:
        utility = (
            0.6 * difficulty_fit
            + 0.25 * (1.0 - np.asarray([float(row["candidate_topic_mastery"]) for row in rows]))
            + 0.15 * coverage
        )
    else:
        utility = (
            0.25 * predicted
            + 0.25 * q_values
            + 0.18 * engagement
            + 0.17 * difficulty_fit
            + 0.15 * coverage
        )
    recent_topics = [str(row["topic_id"]) for row in recent_history[:8] if row.get("topic_id")]
    topic_counts = {
        topic_id: recent_topics.count(topic_id)
        for topic_id in {str(item["topic_id"]) for item in eligible}
    }
    maximum_topic_count = max(topic_counts.values(), default=0)
    recency_penalties = np.asarray(
        [
            min(
                0.35,
                sum(
                    0.20 * (0.7**age)
                    for age, row in enumerate(recent_history)
                    if str(row.get("resource_id")) == str(item.get("id", item.get("resource_id")))
                ),
            )
            for item in eligible
        ],
        dtype=float,
    )
    topic_penalties = np.asarray(
        [0.04 * topic_counts.get(str(item["topic_id"]), 0) for item in eligible],
        dtype=float,
    )
    topic_coverage_bonuses = np.asarray(
        [
            0.12
            * (
                1.0 - topic_counts.get(str(item["topic_id"]), 0) / maximum_topic_count
                if maximum_topic_count
                else 0.0
            )
            for item in eligible
        ],
        dtype=float,
    )
    ranked_utility = utility - recency_penalties - topic_penalties + topic_coverage_bonuses
    order = np.argsort(-ranked_utility, kind="stable")[:top_k]

    out = []
    for index in order:
        candidate = eligible[int(index)]
        resource_id = str(candidate.get("id", candidate.get("resource_id")))
        out.append(
            {
                "action": resource_id,
                "resource_id": resource_id,
                "topic_id": str(candidate["topic_id"]),
                "topic": str(candidate["topic_name"]),
                "resource_type": str(candidate["rtype"]),
                "title": str(candidate.get("title", candidate["topic_name"])),
                "difficulty": round(float(candidate["difficulty"]), 2),
                "duration_min": float(candidate["duration"]),
                "utility": round(float(ranked_utility[index]), 4),
                "explanation": {
                    "predicted_score": round(float(predicted[index]) * 100.0, 1),
                    "difficulty_fit": round(float(difficulty_fit[index]), 3),
                    "engagement": round(float(engagement[index]), 3),
                    "prerequisites_met": True,
                    "coverage": round(float(coverage[index]), 3),
                    "recency_penalty": round(float(recency_penalties[index]), 3),
                    "topic_coverage_bonus": round(float(topic_coverage_bonuses[index]), 3),
                },
            }
        )
    return out


def get_mode() -> str:
    return _load_assets()["mode"]
