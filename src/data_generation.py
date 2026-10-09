"""Generate synthetic learner records across multiple random subject graphs."""

from __future__ import annotations

import os

import numpy as np
import pandas as pd

from src.config import DATA_DIR, N_INTERACTIONS, SEED
from src.domain import (
    catalog_to_frame,
    get_training_domains,
    students_to_frame,
)
from src.env import LearningEnv
from src.feature_schema import RAW_FEATURES, q_action


def behavior_policy(env: LearningEnv, rng: np.random.Generator) -> int:
    """Select a prerequisite-ready topic and a varied resource/difficulty."""
    available = env.available_actions()
    if not available:
        raise RuntimeError("generated topic graph has no prerequisite-ready resources")
    if rng.random() < 0.65:
        weakest = min(
            {env.catalog[index]["topic"] for index in available},
            key=lambda topic: float(env.mastery_est[topic]),
        )
        options = [index for index in available if env.catalog[index]["topic"] == weakest]
    else:
        options = available
    return int(options[int(rng.integers(len(options)))])


def build_dataset(n_interactions: int = N_INTERACTIONS, seed: int = SEED) -> pd.DataFrame:
    rows = []
    catalogs = []
    student_frames = []
    for graph_index, (catalog, students, topics) in enumerate(get_training_domains(seed)):
        graph_id = f"simulated-graph-{graph_index + 1}"
        catalogs.append(catalog_to_frame(catalog).assign(graph_id=graph_id))
        student_frames.append(students_to_frame(students, graph_id))
        env = LearningEnv(
            catalog,
            students,
            topics=topics,
            episode_length=n_interactions,
            seed=seed + graph_index + 11,
        )
        rng = np.random.default_rng(seed + 7 + graph_index)
        for student in students:
            env.reset(student=student)
            for _ in range(n_interactions):
                action = behavior_policy(env, rng)
                features = env.feature_row(action)
                features.update(
                    student_id=student["student_id"],
                    graph_id=graph_id,
                    action=q_action(features),
                )
                _, _, _, outcome = env.step(action)
                features["score"] = outcome["score"]
                features["gain"] = outcome["gain"]
                features["engagement_outcome"] = outcome["engagement"]
                rows.append(features)
    catalogs_frame = pd.concat(catalogs, ignore_index=True)
    catalogs_frame.to_csv(os.path.join(DATA_DIR, "catalog.csv"), index=False)
    pd.concat(student_frames, ignore_index=True).to_csv(
        os.path.join(DATA_DIR, "students.csv"), index=False
    )
    return pd.DataFrame(rows)


def load_or_create(force: bool = False) -> pd.DataFrame:
    path = os.path.join(DATA_DIR, "interactions.csv")
    if os.path.exists(path) and not force:
        existing = pd.read_csv(path)
        if set(RAW_FEATURES).issubset(existing.columns) and "graph_id" in existing.columns:
            return existing
    dataset = build_dataset()
    dataset.to_csv(path, index=False)
    return dataset


def main() -> pd.DataFrame:
    dataset = load_or_create(force=True)
    print(f"[data] interaction log: {dataset.shape[0]} rows x {dataset.shape[1]} columns")
    print(f"[data] simulated topic graphs: {dataset['graph_id'].nunique()}")
    print(f"[data] students: {dataset['student_id'].nunique()}")
    print(f"[data] mean score: {dataset['score'].mean():.2f}")
    return dataset


if __name__ == "__main__":
    main()
