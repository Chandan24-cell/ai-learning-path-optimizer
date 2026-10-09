"""Shared subject-agnostic candidate features and tabular action encoding."""

from __future__ import annotations

from collections.abc import Mapping, Sequence

import numpy as np
import pandas as pd

RESOURCE_TYPES = ("video", "article", "quiz", "interactive", "project")
LEARNING_GOALS = ("exam", "skill", "career", "curiosity")
DIFFICULTY_STEPS = (-2, -1, 0, 1, 2)
PREREQUISITE_THRESHOLD = 0.6
N_Q_STATE_VALUES = 4
N_Q_ACTIONS = len(RESOURCE_TYPES) * len(DIFFICULTY_STEPS)

RAW_FEATURES = (
    "candidate_topic_mastery",
    "prerequisite_mastery_average",
    "difficulty_gap",
    "engagement",
    "recent_score_trend",
    "attempts",
    "resource_type",
    "time",
    "learner_level",
    "learning_goal",
)


def get_topic_mastery(profile: Mapping, topic_id: str) -> float:
    mastery = profile.get("mastery_est", {})
    if isinstance(mastery, Mapping):
        return float(mastery.get(topic_id, 0.25))
    return 0.25


def feature_row(
    profile: Mapping,
    candidate: Mapping,
    prerequisites: Sequence[str] = (),
) -> dict[str, float | str]:
    mastery = get_topic_mastery(profile, str(candidate["topic_id"]))
    prereq_mastery = [get_topic_mastery(profile, item) for item in prerequisites]
    recent = [float(value) for value in profile.get("recent_scores", [])]
    trend = ((recent[-1] - recent[0]) / 100.0) if len(recent) >= 2 else 0.0
    target_difficulty = 1.0 + 4.0 * mastery
    return {
        "candidate_topic_mastery": mastery,
        "prerequisite_mastery_average": float(np.mean(prereq_mastery)) if prereq_mastery else 1.0,
        "difficulty_gap": float(candidate["difficulty"]) - target_difficulty,
        "engagement": float(profile.get("engagement_ma", 0.5)),
        "recent_score_trend": trend,
        "attempts": float(profile.get("attempts", {}).get(str(candidate["topic_id"]), 0)),
        "resource_type": str(candidate["rtype"]),
        "time": float(profile.get("total_time_min", 0.0)),
        "learner_level": float(profile.get("learner_level", 25.0)) / 100.0,
        "learning_goal": str(profile.get("learning_goal", "skill")),
    }


def build_candidate_features(
    profile: Mapping,
    candidates: Sequence[Mapping],
    prerequisites: Mapping[str, Sequence[str]],
) -> pd.DataFrame:
    return pd.DataFrame(
        [
            feature_row(profile, item, prerequisites.get(str(item["topic_id"]), ()))
            for item in candidates
        ],
        columns=RAW_FEATURES,
    )


def build_design_matrix(df: pd.DataFrame) -> pd.DataFrame:
    """Build numeric training/inference inputs with stable categorical columns."""
    result = pd.DataFrame(index=df.index)
    for feature in RAW_FEATURES:
        if feature in {"resource_type", "learning_goal"}:
            continue
        result[feature] = df[feature].astype(float)
    result["log_attempts"] = np.log1p(df["attempts"].astype(float))
    result["log_time"] = np.log1p(df["time"].astype(float))
    for resource_type in RESOURCE_TYPES:
        result[f"rtype_{resource_type}"] = (df["resource_type"] == resource_type).astype(float)
    for goal in LEARNING_GOALS:
        result[f"goal_{goal}"] = (df["learning_goal"] == goal).astype(float)
    return result


def difficulty_step(gap: float) -> int:
    """Map the candidate's signed difficulty gap to one of five action steps."""
    return int(np.clip(round(float(gap)), DIFFICULTY_STEPS[0], DIFFICULTY_STEPS[-1])) + 2


def q_state(row: Mapping[str, float | str], prerequisite_ready: bool) -> tuple[int, ...]:
    mastery_bucket = int(np.digitize(float(row["candidate_topic_mastery"]), [0.3, 0.6, 0.85]))
    gap_bucket = difficulty_step(float(row["difficulty_gap"]))
    engagement_bucket = int(np.digitize(float(row["engagement"]), [0.35, 0.7]))
    return mastery_bucket, gap_bucket, engagement_bucket, int(prerequisite_ready)


def q_action(row: Mapping[str, float | str]) -> int:
    resource_index = RESOURCE_TYPES.index(str(row["resource_type"]))
    return resource_index * len(DIFFICULTY_STEPS) + difficulty_step(float(row["difficulty_gap"]))


def coverage_value(row: Mapping[str, float | str]) -> float:
    """Favor a healthy difficulty range and engaging formats when need is high."""
    need = max(
        1.0 - float(row["candidate_topic_mastery"]),
        1.0 - float(row["engagement"]),
    )
    not_only_easy = float(np.clip((float(row["difficulty_gap"]) + 1.0) / 2.0, 0.0, 1.0))
    engaging_format = float(row["resource_type"] in {"interactive", "project"})
    return float(np.clip(need * (0.65 * not_only_easy + 0.35 * engaging_format), 0, 1))
