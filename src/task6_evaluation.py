"""Task 6 -- evaluate policies and simulated group gaps on unseen topic graphs."""

from __future__ import annotations

import os

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from scipy.stats import ttest_rel

from src.config import DATA_DIR, EPISODE_LENGTH, N_EVAL_STUDENTS, REPORT_DIR, SEED
from src.data_generation import behavior_policy
from src.domain import get_training_domains
from src.env import LearningEnv
from src.feature_schema import q_action, q_state
from src.task5_optimizer import PersonalizedPathOptimizer
from src.utils import banner, gini, save_fig


def _q_action(env: LearningEnv, q_table: dict, rng: np.random.Generator) -> int:
    candidates = env.available_actions()
    scores = []
    for candidate in candidates:
        row = env.feature_row(candidate)
        values = q_table.get(q_state(row, True))
        scores.append(float(values[q_action(row)]) if values is not None else 0.0)
    maximum = max(scores)
    best = [
        candidate for candidate, value in zip(candidates, scores, strict=True) if value == maximum
    ]
    return int(best[int(rng.integers(len(best)))])


def _policy_action(policy, env, step, rng, q_table, optimizer):
    candidates = env.available_actions()
    if policy == "Static curriculum":
        return int(candidates[step % len(candidates)])
    if policy == "Behavior policy":
        return behavior_policy(env, rng)
    if policy == "ZPD heuristic":
        return max(candidates, key=env.zpd_for)
    if policy == "Q-learning":
        return _q_action(env, q_table, rng)
    if policy == "Hybrid optimizer":
        return optimizer.recommend(env)
    raise ValueError(f"Unknown evaluation policy: {policy}")


def _evaluate_policy(policy, student, catalog, topics, q_table, optimizer, seed):
    env = LearningEnv(catalog, [student], topics=topics, episode_length=EPISODE_LENGTH, seed=seed)
    env.reset(student=student)
    rng = np.random.default_rng(seed + 1)
    initial_mastery = float(np.mean(env.mastery))
    for step in range(EPISODE_LENGTH):
        selected = _policy_action(policy, env, step, rng, q_table, optimizer)
        env.step(selected)
    return {
        "student_id": student["student_id"],
        "graph_id": student["graph_id"],
        "ability_group": student["group"],
        "level_group": student["level_group"],
        "engagement_group": "low-engagement" if student["motivation"] < 0.5 else "high-engagement",
        "mastery_group": "low-mastery"
        if float(np.mean(student["prior_mastery"])) < 0.5
        else "higher-mastery",
        "policy": policy,
        "gain": float(np.mean(env.mastery) - initial_mastery),
        "gain_per_hour": float(np.mean(env.mastery) - initial_mastery) / (env.total_time / 60.0),
        "engagement": float(np.mean([row["engagement"] for row in env.trajectory])),
        "final_mastery": float(np.mean(env.mastery)),
        "hours": env.total_time / 60.0,
    }


def _absolute_gap(frame: pd.DataFrame, group_column: str, low: str, high: str) -> float:
    means = frame.groupby(group_column)["gain"].mean()
    return abs(float(means.get(low, 0.0) - means.get(high, 0.0)))


def main(predictor, q_table):
    banner("TASK 6 -- CROSS-GRAPH POLICY AND GROUP-GAP EVALUATION")
    domains = get_training_domains()
    processed_path = os.path.join(DATA_DIR, "processed.npz")
    test_ids = None
    if os.path.exists(processed_path):
        with np.load(processed_path, allow_pickle=True) as data:
            if "test_ids" in data:
                test_ids = set(int(value) for value in data["test_ids"])
    evaluation_domains = []
    for catalog, students, topics in domains:
        selected = [
            student for student in students if test_ids is None or student["student_id"] in test_ids
        ]
        if selected:
            evaluation_domains.append((catalog, selected, topics))
    eval_students = sum((students for _, students, _ in evaluation_domains), [])
    eval_students = eval_students[:N_EVAL_STUDENTS]
    if not eval_students:
        raise ValueError("No held-out simulated learners are available")

    optimizer = PersonalizedPathOptimizer(predictor, q_table)
    policies = [
        "Static curriculum",
        "Behavior policy",
        "ZPD heuristic",
        "Q-learning",
        "Hybrid optimizer",
    ]
    rows = []
    student_count = 0
    for catalog, students, topics in evaluation_domains:
        for student in students:
            if student_count >= N_EVAL_STUDENTS:
                break
            student_count += 1
            for policy in policies:
                seed = SEED + 10_000 + int(student["student_id"])
                rows.append(
                    _evaluate_policy(policy, student, catalog, topics, q_table, optimizer, seed)
                )
    per_student = pd.DataFrame(rows)

    summary_rows = []
    for policy in policies:
        frame = per_student[per_student["policy"] == policy]
        summary_rows.append(
            {
                "policy": policy,
                "gain": float(frame["gain"].mean()),
                "gain_std": float(frame["gain"].std(ddof=1)),
                "gain_per_hour": float(frame["gain"].sum() / frame["hours"].sum()),
                "engagement": float(frame["engagement"].mean()),
                "ability_gap": _absolute_gap(frame, "ability_group", "high-ability", "low-ability"),
                "level_gap": _absolute_gap(frame, "level_group", "high-level", "low-level"),
                "engagement_gap": _absolute_gap(
                    frame, "engagement_group", "high-engagement", "low-engagement"
                ),
                "mastery_gap": _absolute_gap(
                    frame, "mastery_group", "higher-mastery", "low-mastery"
                ),
                "gini_final_mastery": gini(frame["final_mastery"].to_numpy()),
            }
        )
    summary = pd.DataFrame(summary_rows)
    paired = per_student.pivot(index="student_id", columns="policy", values="gain")
    test = ttest_rel(paired["Hybrid optimizer"], paired["Static curriculum"])

    fig, ax = plt.subplots(figsize=(8, 4.5))
    ax.bar(summary["policy"], summary["gain"], color="#2b6cb0")
    ax.set_ylabel("Mean simulated mastery gain")
    ax.set_title(f"Policies on {student_count} learners in held-out graphs")
    ax.tick_params(axis="x", rotation=20)
    ax.grid(alpha=0.25, axis="y")
    save_fig(fig, "task6_policy_comparison.png")

    lines = [
        "# Task 6 -- Cross-Graph Policy Evaluation",
        "",
        (
            f"Evaluation used **{student_count} simulated learners** from topic graphs held out "
            f"from model training, with {EPISODE_LENGTH} interactions per policy."
        ),
        "",
        (
            "| Policy | Mean gain | SD | Gain/hour | Engagement | Ability gap | "
            "Level gap | Engagement gap | "
            "Mastery gap | Final mastery Gini |"
        ),
        "|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for row in summary.to_dict("records"):
        lines.append(
            f"| {row['policy']} | {row['gain']:.4f} | {row['gain_std']:.4f} | "
            f"{row['gain_per_hour']:.4f} | {row['engagement']:.4f} | "
            f"{row['ability_gap']:.4f} | {row['level_gap']:.4f} | "
            f"{row['engagement_gap']:.4f} | "
            f"{row['mastery_gap']:.4f} | {row['gini_final_mastery']:.4f} |"
        )
    lines.extend(
        [
            "",
            (
                "The four group gaps are absolute differences in mean simulated mastery gain "
                "between the named high/low groups. The learner-level gap compares simulated "
                "learners below and above level 50. These are measurements, not proof of fairness."
            ),
            "",
            (
                "The coverage term in Task 5 rewards useful difficulty range and engaging resource "
                "types when mastery or engagement is low; it does not guarantee equal outcomes."
            ),
            "",
            (
                f"Hybrid optimizer versus static curriculum, paired by learner: "
                f"t={float(test.statistic):.3f}, p={float(test.pvalue):.3e}."
            ),
            "",
            (
                "All learners and gains in this evaluation are simulated. These numbers do not "
                "establish real-world learning gains or fairness."
            ),
        ]
    )
    report_path = os.path.join(REPORT_DIR, "task6_evaluation.md")
    with open(report_path, "w", encoding="utf-8") as report:
        report.write("\n".join(lines))
    print(f"[task6] evaluated {student_count} held-out simulated learners")
    print(f"[task6] report -> {report_path}")
    return {"summary": summary, "per_student": per_student, "report_path": report_path}
