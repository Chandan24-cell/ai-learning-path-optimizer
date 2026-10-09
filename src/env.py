"""Simulated learner environment over an arbitrary prerequisite topic graph."""

from __future__ import annotations

import copy
from collections import deque

import numpy as np
import pandas as pd

from src.config import EPISODE_LENGTH, LR_SCALE
from src.domain import sigmoid, zpd_factor
from src.feature_schema import (
    PREREQUISITE_THRESHOLD,
    RAW_FEATURES,
)
from src.feature_schema import (
    feature_row as make_feature_row,
)


class LearningEnv:
    """A single simulated learner with hidden mastery and observed estimates."""

    def __init__(
        self,
        catalog: list[dict],
        students: list[dict],
        topics: list[dict] | None = None,
        episode_length: int = EPISODE_LENGTH,
        seed=None,
    ):
        self.catalog = catalog
        self.students = students
        self.topics = topics or self._topics_from_catalog(catalog)
        self.topic_indices = {topic["topic_id"]: int(topic["index"]) for topic in self.topics}
        self.prerequisites = {
            topic["topic_id"]: tuple(topic.get("prerequisites", ())) for topic in self.topics
        }
        self.episode_length = int(episode_length)
        self.rng = np.random.default_rng(seed)
        self.reset()

    @staticmethod
    def _topics_from_catalog(catalog: list[dict]) -> list[dict]:
        topics = {}
        for entry in catalog:
            topics.setdefault(
                entry["topic_id"],
                {
                    "topic_id": entry["topic_id"],
                    "topic_name": entry["topic_name"],
                    "index": entry["topic"],
                    "prerequisites": entry.get("prerequisites", ()),
                },
            )
        return list(topics.values())

    def reset(self, student=None, student_id=None):
        if student is None:
            if student_id is not None:
                student = self.students[student_id]
            else:
                student = self.students[int(self.rng.integers(len(self.students)))]
        self.student = student
        self.mastery = np.asarray(student["prior_mastery"], dtype=float).copy()
        self.mastery_est = np.clip(
            self.mastery + self.rng.normal(0.0, 0.08, len(self.topics)), 0.0, 1.0
        )
        self.attempts = np.zeros(len(self.topics), dtype=int)
        self.recent_scores: deque[float] = deque(maxlen=5)
        self.total_time = 0.0
        self.engagement_ma = 0.5
        self.last_difficulty = 3.0
        self.last_score = 50.0
        self.t = 0
        self.trajectory: list[dict] = []
        return self.state_vector()

    def clone(self):
        return copy.deepcopy(self)

    @property
    def done(self) -> bool:
        return self.t >= self.episode_length

    def state_vector(self) -> np.ndarray:
        return np.concatenate(
            [
                self.mastery_est,
                [
                    self.last_score / 100.0,
                    min(self.total_time / (self.episode_length * 30.0), 1.5),
                    self.engagement_ma,
                    min(self.attempts.sum() / max(self.episode_length, 1), 1.0),
                    self.last_difficulty / 5.0,
                ],
            ]
        ).astype(np.float32)

    def _profile(self) -> dict:
        return {
            "mastery_est": {
                topic["topic_id"]: float(self.mastery_est[topic["index"]]) for topic in self.topics
            },
            "attempts": {
                topic["topic_id"]: int(self.attempts[topic["index"]]) for topic in self.topics
            },
            "recent_scores": list(self.recent_scores),
            "engagement_ma": self.engagement_ma,
            "total_time_min": self.total_time,
            "learner_level": self.student["learner_level"],
            "learning_goal": self.student["learning_goal"],
        }

    def feature_row(self, action: int) -> dict:
        entry = self.catalog[int(action)]
        return make_feature_row(
            self._profile(),
            entry,
            self.prerequisites.get(str(entry["topic_id"]), ()),
        )

    def available_actions(self) -> list[int]:
        mastery = self._profile()["mastery_est"]
        return [
            index
            for index, entry in enumerate(self.catalog)
            if all(
                mastery.get(prerequisite, 0.25) >= PREREQUISITE_THRESHOLD
                for prerequisite in self.prerequisites.get(str(entry["topic_id"]), ())
            )
        ]

    def step(self, action: int):
        entry = self.catalog[int(action)]
        if int(action) not in self.available_actions():
            raise ValueError("Cannot simulate a resource before its prerequisites are mastered")
        student = self.student
        topic_index = int(entry["topic"])
        mastery = float(self.mastery[topic_index])
        zpd = zpd_factor(mastery, float(entry["difficulty"]))

        goal_adjustment = {"exam": 0.08, "skill": 0.0, "career": 0.04, "curiosity": -0.02}[
            student["learning_goal"]
        ]
        z = (
            1.2 * student["ability"]
            + 2.5 * (mastery - 0.5)
            - 0.8 * (entry["difficulty"] - 3.0)
            + 0.5 * (student["learner_level"] / 100.0 - 0.5)
            + goal_adjustment
        )
        score = float(np.clip(100.0 * (float(sigmoid(z)) + self.rng.normal(0.0, 0.05)), 0, 100))
        gain = LR_SCALE * entry["learning_power"] * zpd * (1.0 - mastery)
        self.mastery[topic_index] = float(np.clip(mastery + gain, 0.0, 1.0))
        engagement = float(
            np.clip(
                entry["engagement_prior"] * (0.4 + 0.6 * student["motivation"]) * (0.5 + 0.5 * zpd),
                0.0,
                1.0,
            )
        )
        mismatch = abs(float(entry["difficulty"]) - (1.0 + 4.0 * mastery))
        reward = 20.0 * gain + engagement - 0.7 * mismatch - 0.02 * entry["duration"]

        self.mastery_est[topic_index] = float(
            np.clip(0.7 * self.mastery_est[topic_index] + 0.3 * score / 100.0, 0.0, 1.0)
        )
        self.recent_scores.append(score)
        self.attempts[topic_index] += 1
        self.total_time += float(entry["duration"])
        self.engagement_ma = 0.7 * self.engagement_ma + 0.3 * engagement
        self.last_difficulty = float(entry["difficulty"])
        self.last_score = score
        self.t += 1

        info = {
            "gain": gain,
            "score": score,
            "engagement": engagement,
            "mismatch": mismatch,
            "topic": topic_index,
            "topic_id": entry["topic_id"],
            "topic_name": entry["topic_name"],
            "rtype": entry["rtype"],
            "duration": entry["duration"],
            "mastery": float(self.mastery[topic_index]),
            "avg_mastery": float(np.mean(self.mastery)),
        }
        self.trajectory.append(info)
        return self.state_vector(), float(reward), self.done, info

    def zpd_for(self, action: int) -> float:
        entry = self.catalog[int(action)]
        return zpd_factor(float(self.mastery_est[int(entry["topic"])]), float(entry["difficulty"]))

    def expected_engagement(self, action: int) -> float:
        entry = self.catalog[int(action)]
        return float(
            np.clip(
                entry["engagement_prior"]
                * (0.4 + 0.6 * self.student["motivation"])
                * (0.5 + 0.5 * self.zpd_for(action)),
                0.0,
                1.0,
            )
        )

    def candidate_features(self) -> pd.DataFrame:
        return pd.DataFrame(
            [self.feature_row(action) for action in self.available_actions()],
            columns=RAW_FEATURES,
        )
