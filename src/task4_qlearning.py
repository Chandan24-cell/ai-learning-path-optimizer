"""Task 4 -- Q-learning over topic-relative learner state and abstract actions."""

from __future__ import annotations

import os

import matplotlib.pyplot as plt
import numpy as np

from src.config import (
    EPISODE_LENGTH,
    MODEL_DIR,
    N_QL_EPISODES,
    QL_ALPHA,
    QL_EPS_END,
    QL_EPS_START,
    QL_GAMMA,
    REPORT_DIR,
    SEED,
)
from src.domain import get_training_domains
from src.env import LearningEnv
from src.feature_schema import N_Q_ACTIONS, q_action, q_state
from src.q_table import save_q_table
from src.utils import banner, save_fig, smooth

Q_TABLE_PATH = os.path.join(MODEL_DIR, "q_table.json")


def train_q_learning(episodes: int = N_QL_EPISODES, seed: int = SEED, verbose: bool = True):
    domains = get_training_domains(seed)
    envs = [
        LearningEnv(catalog, students, topics, episode_length=EPISODE_LENGTH, seed=seed + i + 21)
        for i, (catalog, students, topics) in enumerate(domains)
    ]
    q_table: dict[tuple[int, ...], np.ndarray] = {}
    episode_rewards: list[float] = []
    epsilon = QL_EPS_START
    decay = (QL_EPS_START - QL_EPS_END) / max(int(episodes * 0.7), 1)
    rng = np.random.default_rng(seed + 3)

    for episode in range(episodes):
        env = envs[episode % len(envs)]
        env.reset()
        total_reward = 0.0
        for _ in range(EPISODE_LENGTH):
            candidates = env.available_actions()
            if rng.random() < epsilon:
                chosen = int(candidates[int(rng.integers(len(candidates)))])
            else:
                scores = []
                for candidate in candidates:
                    row = env.feature_row(candidate)
                    state = q_state(row, True)
                    scores.append(
                        float(q_table.setdefault(state, np.zeros(N_Q_ACTIONS))[q_action(row)])
                    )
                maximum = max(scores)
                best = [
                    index
                    for index, value in zip(candidates, scores, strict=True)
                    if value == maximum
                ]
                chosen = int(best[int(rng.integers(len(best)))])

            row = env.feature_row(chosen)
            state = q_state(row, True)
            abstract_action = q_action(row)
            _, reward, done, _ = env.step(chosen)
            next_candidates = env.available_actions()
            next_values = []
            for candidate in next_candidates:
                next_row = env.feature_row(candidate)
                next_key = q_state(next_row, True)
                next_values.append(
                    float(q_table.setdefault(next_key, np.zeros(N_Q_ACTIONS))[q_action(next_row)])
                )
            next_best = max(next_values, default=0.0)
            target = reward + (0.0 if done else QL_GAMMA * next_best)
            state_values = q_table.setdefault(state, np.zeros(N_Q_ACTIONS))
            state_values[abstract_action] += QL_ALPHA * (target - state_values[abstract_action])
            total_reward += reward
            if done:
                break

        epsilon = max(QL_EPS_END, epsilon - decay)
        episode_rewards.append(total_reward)
        if verbose and (episode + 1) % 500 == 0:
            print(
                f"[task4] episode {episode + 1}/{episodes}  eps={epsilon:.3f}  "
                f"avg reward (last 200)={np.mean(episode_rewards[-200:]):.2f}  "
                f"states={len(q_table)}"
            )
    return q_table, episode_rewards


def main(episodes: int = N_QL_EPISODES):
    banner("TASK 4 -- SUBJECT-AGNOSTIC Q-LEARNING")
    q_table, rewards = train_q_learning(episodes=episodes)
    save_q_table(q_table, Q_TABLE_PATH)
    avg_last = float(np.mean(rewards[-200:]))
    avg_first = float(np.mean(rewards[:200]))

    fig, ax = plt.subplots(figsize=(7, 4))
    ax.plot(rewards, alpha=0.25, color="#2b6cb0", label="episode reward")
    smoothed = smooth(rewards, 50)
    ax.plot(np.arange(len(smoothed)) + 25, smoothed, color="#c53030", lw=2, label="moving average")
    ax.set_xlabel("Episode")
    ax.set_ylabel("Cumulative reward")
    ax.set_title("Cross-graph Q-learning")
    ax.legend()
    ax.grid(alpha=0.3)
    save_fig(fig, "task4_qlearning_curve.png")

    lines = [
        "# Task 4 -- Subject-Agnostic Q-Learning",
        "",
        "Training used several randomly generated acyclic topic graphs rather than topic names.",
        "",
        "## State abstraction",
        (
            "Each candidate is represented by mastery bucket, difficulty-gap bucket, engagement "
            "bucket, and prerequisite-ready flag."
        ),
        "",
        "## Abstract action",
        "Actions are the five resource-type labels crossed with five difficulty steps (25 values).",
        "",
        "## Training result",
        f"* Episodes: **{episodes}**",
        f"* Visited abstract states: **{len(q_table)}**",
        f"* Mean episode reward (first 200): **{avg_first:.2f}**",
        f"* Mean episode reward (last 200): **{avg_last:.2f}**",
        f"* Improvement: **{avg_last - avg_first:+.2f}**",
        "",
        (
            "Learner dynamics and all reported outcomes are simulated; they do not demonstrate "
            "real learning gains."
        ),
    ]
    report_path = os.path.join(REPORT_DIR, "task4_rl.md")
    with open(report_path, "w", encoding="utf-8") as report:
        report.write("\n".join(lines))
    print(f"[task4] Q-table saved -> {Q_TABLE_PATH}")
    print(f"[task4] report -> {report_path}")
    return {
        "q_table": q_table,
        "rewards": rewards,
        "report_path": report_path,
        "avg_first": avg_first,
        "avg_last": avg_last,
        "n_states": len(q_table),
    }


if __name__ == "__main__":
    main()
