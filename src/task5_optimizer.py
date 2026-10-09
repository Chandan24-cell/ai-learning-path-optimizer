"""Task 5 -- Novel hybrid personalized learning-path optimizer."""

from __future__ import annotations

import os

import numpy as np
import pandas as pd

from src.config import REPORT_DIR
from src.env import LearningEnv
from src.feature_schema import N_Q_ACTIONS, coverage_value, q_action, q_state
from src.utils import banner


def _minmax(x: np.ndarray) -> np.ndarray:
    lo, hi = float(np.min(x)), float(np.max(x))
    if hi - lo < 1e-9:
        return np.zeros_like(x)
    return (x - lo) / (hi - lo)


class PersonalizedPathOptimizer:
    """Balances four signals:

    * **predicted performance**  -- deep model P(next score | s, a)
    * **expected long-term gain** -- tabular Q-value Q(s, a)
    * **engagement**              -- engagement prior x motivation x ZPD fit
    * **difficulty fit**          -- zone-of-proximal-development kernel
    * **coverage**                -- guards against only-easy work for learners who need support

    The composite score is a convex combination controlled by the weights below,
    which makes the trade-off explicit and auditable.
    """

    def __init__(
        self,
        predictor=None,
        q_table=None,
        catalog=None,
        w_quality: float = 0.25,
        w_value: float = 0.25,
        w_engagement: float = 0.18,
        w_fit: float = 0.17,
        w_coverage: float = 0.15,
    ):
        self.predictor = predictor
        self.q_table = q_table
        self.catalog = catalog
        self.w_quality = w_quality
        self.w_value = w_value
        self.w_engagement = w_engagement
        self.w_fit = w_fit
        self.w_coverage = w_coverage

        total = w_quality + w_value + w_engagement + w_fit + w_coverage
        self.w_quality /= total
        self.w_value /= total
        self.w_engagement /= total
        self.w_fit /= total
        self.w_coverage /= total

    # ------------------------------------------------------------------ core
    def action_scores(self, env: LearningEnv) -> np.ndarray:
        actions = env.available_actions()
        scores = np.full(len(env.catalog), -np.inf, dtype=float)
        if not actions:
            return scores
        rows = [env.feature_row(action) for action in actions]

        # 1. predicted next score (0-1) from the deep model
        if self.predictor is not None:
            feats = pd.DataFrame(rows)
            predicted = self.predictor.predict(feats) / 100.0
        else:
            predicted = np.full(len(actions), 0.5)

        # 2. Candidate-conditioned Q-value for its abstract resource/difficulty action.
        if self.q_table is not None:
            q_norm = np.asarray(
                [
                    float(
                        self.q_table.get(q_state(row, True), np.zeros(N_Q_ACTIONS))[q_action(row)]
                    )
                    for row in rows
                ],
                dtype=float,
            )
            q_norm = _minmax(q_norm)
        else:
            q_norm = np.full(len(actions), 0.5)

        engagement = np.asarray([env.expected_engagement(action) for action in actions])
        fit = np.asarray([env.zpd_for(action) for action in actions])
        coverage = np.asarray([coverage_value(row) for row in rows])
        score = (
            self.w_quality * predicted
            + self.w_value * q_norm
            + self.w_engagement * engagement
            + self.w_fit * fit
            + self.w_coverage * coverage
        )
        scores[np.asarray(actions, dtype=int)] = score
        return scores

    def recommend(self, env: LearningEnv) -> int:
        scores = self.action_scores(env)
        return int(np.argmax(scores))

    def explain(self, env: LearningEnv, top_k: int = 5):
        scores = self.action_scores(env)
        order = np.argsort(-scores)[:top_k]
        rows = []
        for a in order:
            if not np.isfinite(scores[a]):
                continue
            entry = env.catalog[int(a)]
            row = env.feature_row(int(a))
            rows.append(
                dict(
                    action=int(a),
                    topic=entry["topic_name"],
                    resource=entry["rtype"],
                    difficulty=round(entry["difficulty"], 2),
                    duration=entry["duration"],
                    score=round(float(scores[a]), 4),
                    coverage=round(coverage_value(row), 3),
                    prerequisites_met=True,
                )
            )
        return rows

    def plan(self, env: LearningEnv, horizon: int = 10, top_k: int = 3):
        """Greedy multi-step path on a *clone* of the environment."""
        sim = env.clone()
        path = []
        for _ in range(horizon):
            if sim.done:
                break
            scores = self.action_scores(sim)
            available = sim.available_actions()
            order = sorted(available, key=lambda action: scores[action], reverse=True)[:top_k]
            if not order:
                break
            action = int(order[0])
            entry = sim.catalog[action]
            path.append(
                dict(
                    step=len(path) + 1,
                    topic=entry["topic_name"],
                    resource=entry["rtype"],
                    difficulty=round(entry["difficulty"], 2),
                    duration=entry["duration"],
                    alternatives=[
                        f"{sim.catalog[int(a)]['topic_name']}/{sim.catalog[int(a)]['rtype']}"
                        for a in order[1:]
                    ],
                )
            )
            sim.step(action)
        return path


# --------------------------------------------------------------------------
# Entry point
# --------------------------------------------------------------------------
def main(predictor, q_table):
    banner("TASK 5 -- NOVEL PERSONALIZED LEARNING-PATH OPTIMIZER")

    from src.domain import get_domain

    catalog, students = get_domain()

    optimizer = PersonalizedPathOptimizer(predictor, q_table, catalog)

    env = LearningEnv(catalog, students, seed=99)
    env.reset(student=students[0])

    # Warm the learner up using only prerequisite-ready resources.
    for _ in range(5):
        available = env.available_actions()
        env.step(int(available[int(np.random.default_rng(0).integers(len(available)))]))

    print("[task5] composite objective weights:")
    print(
        f"        quality={optimizer.w_quality:.2f}  value={optimizer.w_value:.2f}  "
        f"engagement={optimizer.w_engagement:.2f}  fit={optimizer.w_fit:.2f}  "
        f"coverage={optimizer.w_coverage:.2f}"
    )

    print("\n[task5] top-5 candidate resources for the current learner state:")
    for row in optimizer.explain(env, top_k=5):
        print(
            f"        {row['topic']:<15} {row['resource']:<12} "
            f"difficulty={row['difficulty']}  duration={row['duration']}m  "
            f"score={row['score']}"
        )

    path = optimizer.plan(env, horizon=8, top_k=3)
    print("\n[task5] greedy 8-step personalized path:")
    for step in path:
        print(
            f"        {step['step']}. {step['topic']:<15} {step['resource']:<12} "
            f"difficulty={step['difficulty']}  ({step['duration']} min)  "
            f"alts: {', '.join(step['alternatives'])}"
        )

    # ------------------------------------------------------------ report
    lines = [
        "# Task 5 -- Innovation / Novelty",
        "",
        "## 5.1 Proposed optimizer",
        "`PersonalizedPathOptimizer` combines five complementary signals into a",
        "single auditable utility:",
        "",
        "```",
        "U(s, a) = w_q * P(next_score | s, a)          # deep model: will they succeed?",
        "        + w_v * Q_norm(s, a)                  # RL: long-term learning gain",
        "        + w_e * Engagement(s, a)              # will they stay engaged?",
        "        + w_f * ZPD_fit(s, a)                 # is the difficulty appropriate?",
        "        + w_c * Coverage(s, a)                # avoid only-easy work for learners needing",
        "                                                 # support",
        "```",
        "",
        f"Default weights: quality={optimizer.w_quality:.2f}, value={optimizer.w_value:.2f}, "
        f"engagement={optimizer.w_engagement:.2f}, fit={optimizer.w_fit:.2f}, "
        f"coverage={optimizer.w_coverage:.2f}.",
        "Candidates whose prerequisites are below 0.6 are excluded before ranking.",
        (
            "The coverage term favors a useful difficulty range and engaging formats when mastery "
            "or engagement is low."
        ),
        "",
        "## 5.2 Why this is novel",
        "* Pure collaborative filtering optimises short-term clicks, not learning.",
        "* Pure RL suffers from a cold start and unstable counterfactual estimates.",
        "* Pure difficulty heuristics ignore engagement and long-term value.",
        "* The hybrid **decomposes** the objective, so each term can be monitored,",
        "  re-weighted by pedagogy experts, or audited for fairness.",
        "* Normalized weights and the coverage term make the utility bounded and discourage",
        "  serving only easy resources to weaker or less-engaged learners.",
        "",
        "## 5.3 Multi-step path planning",
        "A greedy rollout on a *cloned* environment produces a horizon-H path,",
        "returning the top-1 recommendation plus top-k alternatives at each step",
        "(useful for UI 'choose your next activity' widgets).",
        "",
        "## 5.4 Example recommendation",
        "| Topic | Resource | Difficulty | Duration | Utility |",
        "|---|---|---|---|---|",
    ]
    for row in optimizer.explain(env, top_k=5):
        lines.append(
            f"| {row['topic']} | {row['resource']} | {row['difficulty']} | "
            f"{row['duration']} min | {row['score']} |"
        )
    lines.extend(
        [
            "",
            "## Evidence and limits",
            (
                "The example is a ranking for one simulated learner state from the offline "
                "pipeline. Utility scores explain the ordering; they are not measured learning "
                "gains. Task 6 evaluates policies on held-out simulated learners."
            ),
            "",
            (
                "All learner profiles and outcomes are simulated. This report does not establish "
                "real learning gains or fairness."
            ),
        ]
    )

    report_path = os.path.join(REPORT_DIR, "task5_optimizer.md")
    with open(report_path, "w", encoding="utf-8") as fh:
        fh.write("\n".join(lines))

    print(f"\n[task5] report -> {report_path}")
    return optimizer, report_path


if __name__ == "__main__":
    from src.q_table import load_q_table
    from src.task3_model import ScorePredictor
    from src.task4_qlearning import Q_TABLE_PATH

    pred = ScorePredictor.load()
    q = load_q_table(Q_TABLE_PATH)
    main(pred, q)
