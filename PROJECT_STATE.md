# Project State

**Updated:** 2026-10-11

## GOAL

Build an adaptive learning-path prototype that runs locally. Students complete a learner profile, choose up to eight subjects from content packs or manual/public-source discovery, and see per-subject progress and improvement guidance. Public-source paths and generated questions are unreviewed drafts. Questions are rule-based from saved, cited Wikipedia/Wikidata material; there is no LLM or paid API. The reinforcement-learning policy and evaluation remain simulation-trained.

The current application is a local multi-subject prototype. Internet subject discovery and lazily generated adaptive quizzes are available through public providers. LLM curriculum/content agents are not implemented.

## CURRENT STATUS

### Works

- FastAPI account, token, onboarding/profile, subject, progress, recommendation, quiz, history, teacher-content, health, and readiness routes.
- SQLite persistence with Alembic migrations, per-subject enrollment/state/history, profile storage, and account deletion.
- Mathematics, Python Programming, and Physics JSON content packs, schema validation, an idempotent single/all-pack import CLI, and a filesystem-backed availability catalog.
- Browser onboarding, subject switching, diagnostic, topic map, recommendation explanation, quizzes, feedback, bounded mastery chart, alternatives, and history. Chart rendering failures show a fallback without interrupting dashboard rendering.
- Required post-profile selection of 1–8 subjects with installed/not-installed pack states, on-demand import/enrollment, manual entry, public-source search/path preview, removable chips, book references, and later dashboard management.
- Eight-active-enrollment API limit across packs and student-owned manual/discovered subjects; student-created subjects enroll immediately and appear in the user's subject list.
- Adding a manual subject automatically searches the configured public providers and builds a cited draft path when sources are available. If discovery fails or finds no path, the empty dashboard explains the cause and offers retry or result selection; existing empty manual subjects have a "Build path from internet" action.
- Enrollment of a pack now also attempts to attach public-source extracts and links; the dashboard exposes a "Start learning" action even before a subject's path/questions are ready.
- The main diagnostic and adaptive quiz flow uses only lazy rule-generated questions with a source URL and generator version. Topics with fewer than five usable questions are marked limited and skipped; self-rating remains available only as an optional weak signal outside the main quiz flow.
- After each graded answer, the existing subject-agnostic predictor/Q-learning/prerequisite recommender is rerun to choose the next eligible topic/resource. Activity sessions allow up to ten questions, prioritize unseen questions, and keep correct answers server-side until grading.
- Invalid on-disk packs are returned as visible catalog errors and logged; `make import-content` imports every valid pack idempotently.
- Public-source search via Wikipedia/Wikidata/OpenAlex and books via Open Library. Discovery fetches use HTTPS host allowlists, public-DNS checks, no redirects/proxies, time/size bounds, response caching, and per-user in-process rate limits.
- Optional 0–5 self-ratings remain labeled as weak signals (not quiz scores), and the weak-topic/improvement view uses real learner data only.
- Rule-based recall questions are generated lazily from saved cited Wikipedia/Wikidata extracts and Wikidata facts. Each item stores its source sentence/link, attribution, generation time/version, and unreviewed status. Banks with fewer than five quality-checked questions are marked limited; weak/no-source topics do not get invented questions.
- Learner-specific quiz sessions prefer unseen questions, adjust question difficulty from mastery/answers, can focus on weak prerequisites, and update mastery only after server grading. Correct answers and source explanations are withheld until grading. Question exposures, learner reports, and teacher review are persisted.
- Account deletion removes learner-owned discovered/manual topics, resources, prerequisite edges, and subjects in addition to learner state.
- Server-side quiz grading; public question responses omit answer keys.
- Prerequisite-aware hybrid recommendation with a ZPD fallback. The current saved predictor and Q-table report `hybrid` from `/ready`.
- Local simulation/training/evaluation pipeline, generated reports, tests, and browser/load/security validation tools.
- Local Render Docker configuration is implemented but not deployed. The image uses pinned runtime-only dependencies, binds Uvicorn to `0.0.0.0:$PORT` (default `10000`), copies only allowlisted serving assets, and uses `/ready` for Render health checks. Missing predictor assets use the existing ZPD fallback.
- Deployment validation completed locally: Docker `linux/amd64` image build succeeded; SQLite and PostgreSQL migrations reached Alembic head in disposable databases; image `/health` returned 200 and `/ready` returned `database: ok` with `hybrid` mode when assets were present. Full pytest passed 85 tests with one PostgreSQL pytest skipped because the host `.venv` lacks psycopg; PostgreSQL migrations were separately run successfully with the image's runtime dependencies.
- User chose to keep generated data, model artifacts, plots, and reports tracked in Git. Local database files and backups are ignored.

### Simulated or incomplete

- Learner records used for model training and evaluation are simulated. No result proves real learning gains, educational outcomes, or real-world fairness.
- `video`, `article`, and similar resource types are labels, not real hosted lessons or media. Each of the three included content packs has six topics and eight draft questions per topic; questions need teacher review.
- The displayed learner level is an estimate initialized from profile self-report and adjusted by a small diagnostic; it is not a qualification.
- Fairness coverage and group gaps are simulated measurements, not guarantees.
- Teacher accounts may self-register. Anyone can create a teacher account and change shared subject content.
- The browser offers next-activity recommendations, not a complete long-form curriculum path.
- Discovered curricula are automated drafts, not teacher-reviewed or verified. Public sources can be incomplete or inaccurate.
- No LLM or paid API is used. Questions are recall-style, auto-generated and unreviewed; verified guardian consent and real learner pilots do not exist.
- Public-source discovery is synchronous at enrollment; provider latency/offline failures are surfaced with retry/search actions rather than background progress tracking. Live preview count depends on suitable provider material and quality filters.

### Broken, slow, or not ready

- **Not ready for public deployment or consequential use.** Teacher provisioning, TLS/reverse proxy, distributed rate limits, data-retention procedures, restore drills, and real accessibility/learning validation remain open.
- Render has not been inspected or deployed from this workspace. The Blueprint, service settings, generated production secret, linked branch, and live service URL still require dashboard review after these local changes are reviewed and pushed.
- Latest local 30-second load matrix: 10 users produced 9.63 requests/second, 440 ms median, 3,500 ms p95, and 0 errors; 100 users produced 10.24 requests/second, 7,400 ms median, 16,000 ms p95, and 0 errors. Authentication dominated endpoint time at high concurrency. These measurements are one-machine observations, not a capacity guarantee.
- The 50-user phase deliberately restarts the server; it recorded 820 connection failures (86.32%) during the interruption and is not a steady-state result. After restart, the probe account logged in and its history remained.
- First metadata/model initialization took 8,314 ms in the load run; the process peaked at about 561 MiB RSS. A separate browser `/ready` check took 9.291 seconds and returned `hybrid`.
- Recommendation repetition is reduced but remains common in the small candidate catalog: the historical eight-profile check measured 63.33%–76.67% duplicate selected actions and 91.61%–92.67% repeated top-five slots. The check also found some initially weak learners had only two eligible choices.
- The latest browser check found no horizontal overflow at 390, 768, and 1440 px and zero axe-core violations on sign-in, dashboard, and quiz. This is not an assistive-technology audit. The Playwright flow now verifies a chart-construction failure is isolated, alternatives still render (or show a clear empty state), the chart stays below 400 px, and browser console errors are absent. An intentionally blocked resource in the separate validation script still generates two browser `ERR_FAILED` console messages.
- SlowAPI 0.1.10 emits three `asyncio.iscoroutinefunction` deprecation warnings in the full pytest run.
- Full pytest emitted one intermittent SQLite connection `ResourceWarning` in the learner-profile test. A focused run with `ResourceWarning` treated as an error passed; the source was not reproduced or conclusively identified.
- Project-configured `mypy` passes. The broader `mypy app src` command still reports legacy simulator typing/stub diagnostics, listed below.

## ARCHITECTURE SUMMARY AND FILE MAP

The browser client in `static/` calls FastAPI routes in `app/routes/`. Services use SQLAlchemy models in `app/models_db.py` and the configured SQLite database. Subject packs in `content/` are validated/imported by `app/content/`. The online recommender in `app/services/recommender.py` loads trusted model files once per process and falls back to prerequisite-aware ZPD scoring if the artifacts are unavailable or incompatible. The simulator, training, and evaluation code is in `src/` and runs through `run_all.py`.

- `app/main.py` — application setup, middleware, and health/readiness routes.
- `app/routes/` — authentication, learning, subjects, and teacher endpoints.
- `app/routes/profile.py`, `app/profile_options.py` — learner profile and data-backed onboarding choices.
- `app/services/` — recommendation, quiz grading, and learner-state updates.
- `app/models_db.py`, `app/database.py`, `app/schemas.py` — database models, engine/session, and API schemas.
- `migrations/` — Alembic schema changes.
- `content/`, `app/content/` — subject/profile data, pack validation, import, and CLI.
- `src/` — simulator, synthetic data, feature schemas, predictor/Q learning, optimizer, and evaluation.
- `run_all.py` — offline generation/training/report command; it overwrites tracked generated artifacts.
- `run_server.py` — local single-process Uvicorn server.
- `static/` — HTML, CSS, JavaScript, and locally served Chart.js.
- `tests/` — pytest, browser, API edge, artifact, security, and load validation.
- `scripts/` — screenshot capture and README chart generation.
- `outputs/data/`, `outputs/models/`, `outputs/plots/`, `outputs/reports/` — retained generated artifacts. `outputs/app.db` is local user data and must not be used for validation.
- `docs/` — API, architecture, data, security, assignment, and validation documentation.
- `Makefile` — setup, train, migrate, run, test, lint, and clean targets.

## ROADMAP

| Phase | Status | Focus |
|---|---|---|
| S — Project state and stabilization | Complete | Handoff, novelty/coverage work, usability feedback, profiling, pool tuning, and validation. |
| A — Onboarding and learner profile | Complete | Consent notice, profile, data-driven country choices, and per-subject learner level/goal. |
| B — Curriculum/content agents | Future | Teacher-reviewed curriculum/content authoring. LLM agents are not implemented. |
| C — Adaptive learning paths | Future | Multi-step, beginner-to-advanced sequencing and mastery explanations. |
| D — Policy and learner outcomes | Future | More robust evaluation and appropriately governed evidence beyond simulation. |
| E — Student and teacher experience | Future | Trusted teacher provisioning, privacy, accessibility, and content workflows. |
| F — Final cleanup and local release | Complete, local demo only | Cleanup, local quality checks, documentation, and release-readiness evidence. Public deployment is not ready. |
| G — Subject enrollment and internet discovery | Complete, local prototype | Eight-subject onboarding, public-source drafts, provenance, no-quiz/self-rating behavior, and improvement view. No LLM; RL stays simulation-trained. |
| H — Rule-based quizzes and adaptive questions | Complete, local prototype | Source-grounded, unreviewed recall questions, adaptive per-learner sessions, opt-in sample packs, tests, and migration `0006`; no LLM or paid API. |

## DECISIONS LOG

| Date | Decision | Reason |
|---|---|---|
| 2026-10-10 | Keep SQLite as the local default; do not migrate to PostgreSQL in this phase. | The latest local test showed no SQLite lock messages, but one-machine results do not decide production database capacity. |
| 2026-10-10 | Keep the existing 40-connection SQLite pool and single-process local server setup. | Pool sizing removed the previously reproduced connection-pool 500s. The latest p95 remains high; weakening password hashing is not an acceptable performance shortcut. |
| 2026-10-10 | Keep checked-in generated datasets, models, plots, and reports. | The owner explicitly chose to retain current generated outputs in Git. Back them up before retraining. |
| 2026-10-10 | Use MIT License with copyright notice for Chandan Kumar Sah. | The owner selected MIT and provided the copyright-holder name. |
| 2026-10-10 | Bound the mastery chart and isolate chart errors from the rest of dashboard rendering. | Chart.js initialization could abort recommendation rendering; the dashboard now reports chart failures and continues to show alternatives. |
| 2026-10-10 | Restrict Phase G migration validation to a newly created temporary database; preserve `outputs/app.db`. | Existing local learner data must not be modified without explicit approval. |
| 2026-10-11 | After explicit approval, back up the local database and apply migration `0005_subject_discovery`. | The running app was using the model from revision `0005` while the database remained at `0004`, causing profile updates to fail on the missing `self_ratings_json` column. |
| 2026-10-11 | After explicit approval, back up the local database and apply migration `0006_rule_based_quizzes`. | Manual subject creation was querying `topics.source_extract`, which was added in `0006`; the local database was still at `0005`. |
| 2026-10-10 | Keep discovered subjects as drafts and store only short summaries, provenance, bibliographic metadata, and links. | Public web content is untrusted and copyright-restricted; teachers must review paths and no quiz content is invented. |
| 2026-10-10 | Enforce eight enrollments in the current single-process API and document the process-local lock. | This meets the local-server behavior without introducing a distributed enrollment counter. |
| 2026-10-11 | Discover packs from validated `content/*/content.json` files, expose install state/errors, and import/enroll selected missing packs on demand. | The database-only catalog hid valid packs that had not yet been imported. |
| 2026-10-11 | Immediately enroll student-owned manual/discovered subjects when created. | Personal subjects must appear in My Subjects and consume one of the same eight slots. |
| 2026-10-11 | Generate only rule-based recall questions from persisted cited source extracts and structured Wikidata facts; do not call an LLM or paid API. | Keep questions traceable to available evidence and fail closed when the source cannot support quality checks. |
| 2026-10-11 | Keep generated questions unreviewed; mark banks under five accepted questions as limited, and allow self-rating only as a separate weak signal. | Avoid presenting sparse or automatic material as a complete verified quiz. |
| 2026-10-11 | Move the three bundled packs under `content/examples/` and hide them from the default subject catalog, with an explicit sample-subject option. | New learners should start with no fixed/pre-enrolled subjects while retaining opt-in demonstration content. |
| 2026-10-11 | Require question distractors to match broad answer type and use only same-subject sibling topics for definition questions. | The source supports a valid answer, but distractor design must not introduce unrelated fact types or terms as topic choices. |
| 2026-10-11 | Teacher approval is stored as `teacher-approved`; the API accepts `approved` as the request value. | Keep a distinct persisted state for content that has passed teacher review. |
| 2026-10-11 | Automatically try public-source path discovery for manually added subjects, while retaining an explicit retry and result-picking path when discovery fails. | New and previously empty manual subjects should not leave learners at an unexplained blank dashboard; discovered materials still use the Phase H lazy, cited question flow. |
| 2026-10-12 | Keep internet-source questions as the only questions in the primary learner quiz flow, skip limited banks, and rerun the existing recommender after each graded response. | Pack-authored legacy questions are not guaranteed to have public provenance; use only generated questions with stored source links and keep quiz scores grounded in graded answers. |
| 2026-10-12 | Cap an adaptive activity session at ten questions and retain unseen-first selection. | Provide a useful learning run while keeping sessions bounded and avoiding repeats until a bank is exhausted. |

## KNOWN ISSUES AND RISKS

- Public teacher self-registration permits edits to shared learning content.
- The 100-user local test has a 16-second p95 and high authentication latency. Do not treat it as production capacity; do not reduce bcrypt strength to improve it.
- The 50-user load phase includes a planned restart and cannot be read as a steady-state failure rate.
- Some profiles receive a narrow set of eligible recommendations; novelty work does not eliminate repeated recommendation slots.
- The first model-using request takes several seconds and uses substantial memory.
- SlowAPI emits deprecation warnings; pytest intermittently reports a SQLite unclosed-connection warning.
- Repository-wide `ruff format --check .` flags `scripts/make_readme_plots.py`; formatting checks pass when that unrelated file is excluded.
- `mypy app src` has 34 known diagnostics, detailed in [docs/VALIDATION_REPORT.md](docs/VALIDATION_REPORT.md) and summarized below. Project-configured `mypy` passes.
- Tokens are in browser local storage; an access token remains usable until expiry after logout.
- The under-18 notice is not guardian-consent verification. No formal privacy impact, accessibility, or legal review has been completed.
- TensorFlow is pinned to a release-candidate build; platform installation may vary.
- SQLite, one local server process, and process-local rate limits are not validated for multi-worker production.
- Public source data can be wrong or unsuitable; discovered paths and rule-generated questions remain unreviewed drafts. Questions are recall-style, depend on stored source coverage, and may be absent or marked limited.
- Manual subject path creation depends on public discovery services being reachable. If no useful result is available, the subject remains enrolled but its dashboard explains the failure and offers retry or result selection.
- `outputs/app.db` is at revision `0006_rule_based_quizzes`. It was migrated only after explicit approval, after a protected backup was made at `outputs/app.db.before-0006-20261011-1258`. Before applying future migrations to this data, make a new backup and get approval.
- Enrollment count enforcement, discovery request limits, and discovery response caching are process-local; multi-worker deployment would need shared coordination.
- The eight-enrollment limit uses an in-process lock, not a cross-process/database constraint. Discovery rate limits/cache are also process-local. Migration `0005_subject_discovery` has a protected pre-migration backup at `outputs/app.db.before-migration-20261011-0050`; migration `0006_rule_based_quizzes` has a protected pre-migration backup at `outputs/app.db.before-0006-20261011-1258`.
- Pack discovery depends on valid `content.json` files being present locally. Validation errors are surfaced in the API/UI and server log; the latest temporary-database `make import-content` check imported all three built-in packs.
- Do not use synthetic metrics to make real learner decisions.

## HOW TO RUN AND TEST

From the repository root:

```sh
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -r requirements.txt -r requirements-dev.txt
cp .env.example .env
```

Replace the placeholder `APP_SECRET` with a private random value and keep it stable for the same database. Back up `outputs/models/` before training; `make train` overwrites generated data, models, plots, and reports. Run `make migrate` before starting updated app code; it targets `outputs/app.db`. Back up any existing local database and obtain approval before applying migrations.

```sh
make train
# For a live local database only, make migrate after an approved backup.
make import-content
make run
```

The optional real-provider smoke test prompts for local credentials:

```sh
python scripts/try_discovery.py --query "astronomy"
```

The local app is at `http://127.0.0.1:8000/`; Swagger is at `/docs`. Run checks in another terminal:

```sh
playwright install chromium
pytest
ruff check .
ruff format --check .
mypy
pre-commit run --all-files
.venv/bin/bandit -q -r app src
.venv/bin/python -m pip_audit -r requirements.txt -r requirements-dev.txt
```

The latest full regression run for automatic subject learning passed 78 tests with 80.06% coverage. The saved-source Playwright flow covers discovery onboarding, ten distinct graded questions, feedback, mastery and recommendation updates, chart bounds, manual/offline recovery, and zero browser console errors. Offline subjects with no cited quiz content can complete setup without fabricated answers or an estimated-level change. The real-provider `scripts/try_questions.py "computer networking"` preview returned ten source-linked questions in this run; availability and question quality depend on the public sources and the rule-based quality filters. The browser test can take several minutes while its isolated server and recommender initialize.

`ruff check .`, configured `mypy`, Bandit, and pip-audit pass. `ruff format --check --exclude scripts/make_readme_plots.py .` passes; the unfiltered check still flags only `scripts/make_readme_plots.py`, an unrelated pre-existing formatting issue. This task did not change `outputs/app.db`. For the earlier manual-subject schema issue, migration `0006_rule_based_quizzes` was applied after approval and backup; database integrity is `ok`, its revision is `0006_rule_based_quizzes`, and user/enrollment/topic/question row counts match the pre-migration backup.

## BROADER MYPY DIAGNOSTICS

`mypy app src` was run with mypy 2.1.0 and reported 34 errors across 10 files. The errors are recorded individually below rather than hidden:

| File and line | Diagnostic |
|---|---|
| `src/feature_schema.py:8` | Missing library stubs for `pandas`. |
| `src/domain.py:6` | Missing library stubs for `pandas`. |
| `src/env.py:9` | Missing library stubs for `pandas`. |
| `src/env.py:46` | Local `topics` needs a type annotation. |
| `src/data_generation.py:8` | Missing library stubs for `pandas`. |
| `src/utils.py:20` | Missing library stubs for `tensorflow`. |
| `src/utils.py:30` | Returning `Any` from a function declared to return an ndarray. |
| `src/task2_preprocessing.py:7` | `joblib` is installed but has no stubs or `py.typed` marker. |
| `src/task2_preprocessing.py:10` | Missing library stubs for `pandas`. |
| `src/task2_preprocessing.py:11` | `sklearn.decomposition` is installed but has no stubs or `py.typed` marker. |
| `src/task2_preprocessing.py:12` | `sklearn.feature_selection` is installed but has no stubs or `py.typed` marker. |
| `src/task2_preprocessing.py:13` | `sklearn.preprocessing` is installed but has no stubs or `py.typed` marker. |
| `src/task2_preprocessing.py:78` | A value typed as possibly `None` has no `transform` attribute. |
| `src/task2_preprocessing.py:91` | A value typed as possibly `None` has no `transform` attribute. |
| `src/task2_preprocessing.py:93` | Returning `Any` from a function declared to return an ndarray. |
| `src/task2_preprocessing.py:200` | A value typed as possibly `None` has no `head` attribute. |
| `src/task3_model.py:8` | `joblib` is installed but has no stubs or `py.typed` marker. |
| `src/task3_model.py:11` | `sklearn.metrics` is installed but has no stubs or `py.typed` marker. |
| `src/task3_model.py:18` | Missing library stubs for `tensorflow`. |
| `src/task3_model.py:20` | Missing library stubs for `tensorflow.keras`. |
| `src/task3_model.py:148` | `sklearn.neural_network` is installed but has no stubs or `py.typed` marker. |
| `src/task3_model.py:192` | A value typed as `dict[str, Any] | None` is indexed. |
| `src/task3_model.py:193` | A value typed as `dict[str, Any] | None` is indexed. |
| `src/task3_model.py:196` | A value typed as `dict[str, Any] | None` is indexed. |
| `src/task3_model.py:201` | A value typed as `dict[str, Any] | None` is indexed. |
| `src/task3_model.py:203` | A value typed as `dict[str, Any] | None` is indexed. |
| `src/task3_model.py:221` | A value typed as `dict[str, Any] | None` is indexed. |
| `src/task3_model.py:230` | A value typed as `dict[str, Any] | None` is indexed. |
| `src/task3_model.py:277` | A value typed as `dict[str, Any] | None` is indexed. |
| `src/task5_optimizer.py:8` | Missing library stubs for `pandas`. |
| `src/task5_optimizer.py:136` | Local `path` needs a type annotation. |
| `app/services/recommender.py:97` | Redundant cast to a dictionary of ndarray values. |
| `src/task6_evaluation.py:9` | Missing library stubs for `pandas`. |
| `src/task6_evaluation.py:10` | Missing library stubs for `scipy.stats`. |

## MODEL HANDOFF NOTES

- Read this file and [AGENTS.md](AGENTS.md) before changing the project. Update this file at the end of every task.
- Keep work local. Do not add a Git remote, push, create GitHub Actions, or deploy to a cloud service.
- Preserve `outputs/app.db`; use temporary SQLite databases for tests and validation. Any future migration of the local database requires explicit approval and a protected backup first.
- The owner chose to keep generated `outputs/data/`, `outputs/models/`, `outputs/plots/`, and `outputs/reports/` tracked. Back up models before running `make train` and review generated diffs.
- Do not include `correct_option` in public question responses. Quiz grading stays on the server.
- Do not collect age, birth date, institution name, or more identifying fields without explicit approval and privacy review. Profile choices live in `content/learner-profile/options.json`.
- Treat learner level as a heuristic and all model metrics as simulated behavior checks, not educational evidence.
- Keep subject behavior in content packs; do not add subject-name-specific conditions to application code.
- Do not claim verified discovery accuracy, implemented LLM authoring agents, guardian verification, real learning gains, or production-scale capacity.
- The project license is MIT; retain the copyright name given by the owner.
