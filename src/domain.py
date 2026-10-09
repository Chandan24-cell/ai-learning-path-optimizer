"""Synthetic learner and resource generation across prerequisite topic graphs."""

from __future__ import annotations

import numpy as np
import pandas as pd

from src.config import (
    N_STUDENTS,
    RESOURCE_PROFILE,
    RESOURCE_TYPES,
    SEED,
    ZPD_SIGMA,
)

_EDUCATION_LEVELS = (
    (17, "primary"),
    (32, "middle_school"),
    (49, "high_school"),
    (66, "undergraduate"),
    (82, "postgraduate"),
    (94, "phd"),
    (100, "professional"),
)
_LEARNING_GOALS = ("exam", "skill", "career", "curiosity")


def sigmoid(x):
    return 1.0 / (1.0 + np.exp(-np.asarray(x, dtype=float)))


def zpd_factor(mastery: float, difficulty: float) -> float:
    target = 1.0 + 4.0 * mastery
    return float(np.exp(-((difficulty - target) ** 2) / (2.0 * ZPD_SIGMA**2)))


def mathematics_graph() -> list[dict]:
    names = [
        "Algebra",
        "Geometry",
        "Probability",
        "Calculus",
        "Statistics",
        "Linear Algebra",
    ]
    ids = [
        "mathematics.algebra",
        "mathematics.geometry",
        "mathematics.probability",
        "mathematics.calculus",
        "mathematics.statistics",
        "mathematics.linear-algebra",
    ]
    difficulty = [1.5, 2.0, 3.0, 3.8, 3.0, 3.4]
    prerequisite_indices = [(), (), (0,), (0,), (2,), (0,)]
    return [
        {
            "topic_id": ids[index],
            "topic_name": name,
            "index": index,
            "base_difficulty": difficulty[index],
            "prerequisites": tuple(ids[item] for item in prerequisite_indices[index]),
        }
        for index, name in enumerate(names)
    ]


def make_random_graphs(seed: int = SEED, count: int = 4) -> list[list[dict]]:
    """Create distinct DAGs; prerequisite edges always point to earlier nodes."""
    rng = np.random.default_rng(seed)
    graphs = []
    for graph_index in range(count):
        count_topics = int(rng.integers(5, 9))
        graph_id = f"simulated-graph-{graph_index + 1}"
        topics = []
        for topic_index in range(count_topics):
            prerequisite_indices = [
                earlier for earlier in range(topic_index) if rng.random() < 0.24
            ]
            topics.append(
                {
                    "topic_id": f"{graph_id}.topic-{topic_index + 1}",
                    "topic_name": f"Topic {topic_index + 1}",
                    "index": topic_index,
                    "base_difficulty": float(rng.uniform(1.2, 4.6)),
                    "prerequisites": tuple(
                        f"{graph_id}.topic-{index + 1}" for index in prerequisite_indices
                    ),
                }
            )
        graphs.append(topics)
    return graphs


def make_catalog(topics: list[dict], rng: np.random.Generator) -> list[dict]:
    catalog = []
    for topic in topics:
        for resource_type in RESOURCE_TYPES:
            power, engagement, duration, difficulty_offset = RESOURCE_PROFILE[resource_type]
            difficulty = float(
                np.clip(
                    topic["base_difficulty"] + difficulty_offset + rng.normal(0.0, 0.25),
                    1.0,
                    5.0,
                )
            )
            catalog.append(
                {
                    "resource_id": f"{topic['topic_id']}.{resource_type}",
                    "topic_id": topic["topic_id"],
                    "topic": int(topic["index"]),
                    "topic_name": topic["topic_name"],
                    "rtype": resource_type,
                    "difficulty": difficulty,
                    "duration": float(duration),
                    "learning_power": float(power),
                    "engagement_prior": float(engagement),
                    "prerequisites": topic["prerequisites"],
                }
            )
    return catalog


def make_students(n: int, topics: list[dict], rng: np.random.Generator, id_offset: int = 0) -> list:
    students = []
    for index, ability in enumerate(rng.normal(0.0, 1.0, n)):
        motivation = float(np.clip(rng.beta(2, 2), 0.05, 1.0))
        learner_level = float(rng.uniform(0, 100))
        learner_level_label = next(
            label for maximum, label in _EDUCATION_LEVELS if learner_level <= maximum
        )
        learning_goal = str(rng.choice(_LEARNING_GOALS))
        prior = np.clip(
            0.10
            + 0.45 * learner_level / 100.0
            + 0.10 * ability
            + rng.normal(0.0, 0.08, len(topics)),
            0.0,
            0.95,
        )
        students.append(
            {
                "student_id": id_offset + index,
                "ability": float(ability),
                "motivation": motivation,
                "learner_level": learner_level,
                "learner_level_label": learner_level_label,
                "learning_goal": learning_goal,
                "prior_mastery": prior.astype(float),
                "group": "high-ability" if ability >= 0.0 else "low-ability",
                "level_group": "high-level" if learner_level >= 50.0 else "low-level",
            }
        )
    return students


_CACHE: dict[tuple[str, int], tuple[list[dict], list[dict], list[dict]]] = {}


def get_domain(seed: int = SEED):
    """Compatibility domain using the project's original Mathematics curriculum."""
    key = ("mathematics", seed)
    if key not in _CACHE:
        topics = mathematics_graph()
        rng = np.random.default_rng(seed)
        catalog = make_catalog(topics, rng)
        students = make_students(N_STUDENTS, topics, rng)
        _CACHE[key] = (catalog, students, topics)
    catalog, students, _topics = _CACHE[key]
    return catalog, students


def get_training_domains(seed: int = SEED) -> list[tuple[list[dict], list[dict], list[dict]]]:
    """Return several independent random prerequisite graphs for model training."""
    result = []
    student_offset = 0
    for graph_index, topics in enumerate(make_random_graphs(seed)):
        rng = np.random.default_rng(seed + 101 + graph_index)
        catalog = make_catalog(topics, rng)
        students = make_students(
            max(1, N_STUDENTS // 4),
            topics,
            rng,
            id_offset=student_offset,
        )
        for student in students:
            student["graph_id"] = f"simulated-graph-{graph_index + 1}"
        student_offset += len(students)
        result.append((catalog, students, topics))
    return result


def catalog_to_frame(catalog) -> pd.DataFrame:
    return pd.DataFrame(catalog)


def students_to_frame(students, graph_id: str = "mathematics") -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "student_id": student["student_id"],
                "graph_id": graph_id,
                "ability": student["ability"],
                "motivation": student["motivation"],
                "learner_level": student["learner_level"],
                "learner_level_label": student["learner_level_label"],
                "learning_goal": student["learning_goal"],
                "group": student["group"],
                "level_group": student["level_group"],
                "mean_prior_mastery": float(np.mean(student["prior_mastery"])),
            }
            for student in students
        ]
    )
