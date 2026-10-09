# Task 5 -- Innovation / Novelty

## 5.1 Proposed optimizer
`PersonalizedPathOptimizer` combines five complementary signals into a
single auditable utility:

```
U(s, a) = w_q * P(next_score | s, a)          # deep model: will they succeed?
        + w_v * Q_norm(s, a)                  # RL: long-term learning gain
        + w_e * Engagement(s, a)              # will they stay engaged?
        + w_f * ZPD_fit(s, a)                 # is the difficulty appropriate?
        + w_c * Coverage(s, a)                # avoid only-easy work for learners needing
                                                 # support
```

Default weights: quality=0.25, value=0.25, engagement=0.18, fit=0.17, coverage=0.15.
Candidates whose prerequisites are below 0.6 are excluded before ranking.
The coverage term favors a useful difficulty range and engaging formats when mastery or engagement is low.

## 5.2 Why this is novel
* Pure collaborative filtering optimises short-term clicks, not learning.
* Pure RL suffers from a cold start and unstable counterfactual estimates.
* Pure difficulty heuristics ignore engagement and long-term value.
* The hybrid **decomposes** the objective, so each term can be monitored,
  re-weighted by pedagogy experts, or audited for fairness.
* Normalized weights and the coverage term make the utility bounded and discourage
  serving only easy resources to weaker or less-engaged learners.

## 5.3 Multi-step path planning
A greedy rollout on a *cloned* environment produces a horizon-H path,
returning the top-1 recommendation plus top-k alternatives at each step
(useful for UI 'choose your next activity' widgets).

## 5.4 Example recommendation
| Topic | Resource | Difficulty | Duration | Utility |
|---|---|---|---|---|
| Algebra | interactive | 1.74 | 25.0 min | 0.728 |
| Algebra | quiz | 1.89 | 10.0 min | 0.6742 |
| Algebra | project | 1.51 | 45.0 min | 0.6122 |
| Algebra | video | 1.0 | 12.0 min | 0.5417 |
| Algebra | article | 1.0 | 18.0 min | 0.5224 |

## Evidence and limits
The example is a ranking for one simulated learner state from the offline pipeline. Utility scores explain the ordering; they are not measured learning gains. Task 6 evaluates policies on held-out simulated learners.

All learner profiles and outcomes are simulated. This report does not establish real learning gains or fairness.