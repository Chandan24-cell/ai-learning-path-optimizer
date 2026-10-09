"""Task 1 -- Problem analysis."""

from __future__ import annotations

import os

from src.config import REPORT_DIR, RESOURCE_TYPES
from src.feature_schema import DIFFICULTY_STEPS, N_Q_ACTIONS
from src.utils import banner

REPORT = f"""# Task 1 -- Problem Analysis

## 1.1 Problem statement
Given a stream of learner evidence (quiz scores, time-on-task, topic-level
mastery estimates, resource usage, assessment attempts), recommend the **next
learning activity** that maximises long-run learning gain while keeping the
learner engaged and the difficulty appropriate.

Formally: learn a policy

    pi(a | s)  ->  a* = argmax_a  E[ sum_t gamma^t r_t ]

where `a` is a learning resource and `s` is the learner state.

## 1.2 Data available
| Source | Fields | Role |
|---|---|---|
| Quiz / assessment attempts | score (0-100), attempt count per topic | performance signal |
| Learning time | minutes per resource, cumulative time | cost / effort |
| Topic mastery | estimated mastery per topic (0-1) | state |
| Resource usage | resource type, difficulty, duration | action space |
| Engagement | moving average of engagement proxy | state / reward |

## 1.3 State
For each candidate resource, use topic mastery, prerequisite mastery average,
difficulty gap from the learner's estimated level, engagement, recent score
trend, attempts, resource type, cumulative learning time, a self-reported
learner level (0-100), and learning goal. Topic names and IDs are metadata,
not model features. The level is a heuristic initialized from education
category and adjusted by a short diagnostic.

The learner's **true** knowledge is latent and never observed; the platform only
holds a noisy estimate updated from observed scores.

## 1.4 Action space
The available actions are candidate resources in the enrolled subject whose
prerequisites are mastered. Q-learning uses {N_Q_ACTIONS} abstract actions:
the {len(RESOURCE_TYPES)} resource types ({", ".join(RESOURCE_TYPES)}) crossed
with {len(DIFFICULTY_STEPS)} relative difficulty steps ({DIFFICULTY_STEPS}).

## 1.5 Desired output
A ranked recommendation of the next resource, plus a multi-step learning path,
optimising a composite objective:

    reward = w1 * learning_gain - w2 * difficulty_mismatch
             + w3 * engagement - w4 * time_cost

## 1.6 Why it is hard
* **Cold start** -- a short diagnostic quiz estimates topic mastery at enrollment.
* **Prerequisites** -- blocked topics must stay out of recommendations until ready.
* **Transfer** -- the model must generalize across different subject graphs.
* **Delayed reward** -- a resource's benefit only shows up later.
* **Non-stationarity** -- the learner changes as they learn.
* **Counterfactuals** -- logged data reflects the old (behaviour) policy.
* **Fairness** -- the policy must not systematically starve a subgroup.
"""


def write_report() -> str:
    path = os.path.join(REPORT_DIR, "task1_problem_analysis.md")
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(REPORT)
    return path


def main() -> str:
    banner("TASK 1 -- PROBLEM ANALYSIS")
    path = write_report()
    print(REPORT)
    print(f"[task1] report written -> {path}")
    return path


if __name__ == "__main__":
    main()
