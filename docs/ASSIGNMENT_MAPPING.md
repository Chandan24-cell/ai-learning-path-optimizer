# Assignment mapping

This map links Tasks 1–7 to the current source and checked-in generated reports. Task reports are generated under `outputs/reports/` by the corresponding `src/task*.py` module. The checked-in data and model artifacts were generated for the generalized, subject-agnostic pipeline. All generated learner examples and reported outcomes are simulated.

| Task | What it covers | Main implementation | Generated report |
|---|---|---|---|
| 1 — Problem analysis | Subject-agnostic decision problem, candidate-specific features, prerequisites, abstract actions, cold start, and fairness concerns. | `src/task1_problem_analysis.py`, `src/feature_schema.py` | `outputs/reports/task1_problem_analysis.md` |
| 2 — Data transformation | Generates synthetic examples across random prerequisite graphs, splits by graph, transforms candidate features, selects features, and records split identifiers. | `src/data_generation.py`, `src/domain.py`, `src/task2_preprocessing.py`, `src/feature_schema.py` | `outputs/reports/task2_preprocessing.md` |
| 3 — Predictive model | Trains the next-score predictor using the preprocessing pipeline; supports the TensorFlow backend and configured scikit-learn fallback. | `src/task3_model.py`, `src/task2_preprocessing.py` | `outputs/reports/task3_model.md` |
| 4 — Reinforcement learning | Trains a tabular Q policy using mastery, difficulty-gap, engagement, and prerequisite-ready state buckets with abstract resource-type/difficulty actions. | `src/task4_qlearning.py`, `src/q_table.py`, `src/feature_schema.py`, `src/env.py` | `outputs/reports/task4_rl.md` |
| 5 — Optimizer | Ranks prerequisite-eligible candidate resources using predicted score, normalized Q value, engagement, difficulty fit, and coverage; documents a multi-step simulator plan. | `src/task5_optimizer.py`, `app/services/recommender.py`, `src/feature_schema.py` | `outputs/reports/task5_optimizer.md` |
| 6 — Evaluation | Compares policies on held-out simulated topic graphs and computes ability, engagement, and mastery group gaps. | `src/task6_evaluation.py`, `src/task5_optimizer.py`, `src/domain.py`, `src/env.py` | `outputs/reports/task6_evaluation.md` |
| 7 — Conclusion | Summarizes the prototype, simulation-only evidence, technical limitations, and work needed before real-world use. | `src/task7_conclusion.py` | `outputs/reports/task7_conclusion.md` |

## Cross-task platform support

- `content/*/content.json`, `app/content/`, and `app/models_db.py` define and load subject data.
- `migrations/versions/0002_subject_platform.py` migrates legacy Mathematics progress into subject-scoped learner state.
- `app/routes/subjects.py` and `app/services/subject_learning.py` provide subject enrollment, diagnostic, progress, recommendation, quiz, history, and teacher-content workflows.
- `app/services/recommender.py` is the online candidate ranker and uses a prerequisite-aware ZPD fallback when the expected model assets are unavailable or incompatible.
- `tests/test_subject_platform.py`, the API/service tests, and `tests/test_browser_flow.py` exercise platform behavior.

## Evidence status

The checked-in pipeline artifacts include synthetic data, a predictor, a Q table, plots, and Task 1–7 reports. In the current validation environment `/ready` reports `hybrid`. Run `make train` to regenerate those tracked artifacts, then review the diff before keeping any generated changes. All learner profiles and outcomes are simulated; a successful run tests behavior only and does not prove real learning gains.
