# Changelog

All notable project changes are listed here. This file summarizes the stabilization, security, documentation, validation, and multi-subject phases.

## [Unreleased]

### Automatic subject learning flow

- Run public-source discovery and build source-backed topic material when a learner enrolls in a pack or creates a manual subject; show retry/search recovery when discovery is offline or finds no path.
- Gate learning recommendations and quizzes to lazily generated, cited Wikipedia/Wikidata questions. Skip limited banks instead of making self-rating the main activity.
- Start a short diagnostic from the dashboard, then re-run the existing predictor/Q-learning/prerequisite recommender after every graded answer; cap an activity session at ten questions and preserve unseen-first selection.
- Expanded the saved-source Playwright flow to cover discovery onboarding, manual/offline messaging, grading feedback, ten distinct questions, mastery/recommendation updates, chart rendering, and browser errors.
- Improved `scripts/try_questions.py` to search multiple Wikipedia candidates and use complete source sentences. Live question preview remains subject to provider availability; no questions are fabricated to meet a count.
- Added regression coverage confirming an offline, empty subject can finish setup without fabricated quiz answers or a false learner-level increase.

### Phase H — rule-based quizzes and adaptive questions

- Added lazy rule-based recall questions sourced only from saved, cited Wikipedia/Wikidata extracts and facts. Questions retain short source sentences, links, attribution, generator version and an unreviewed status; small banks are marked limited rather than padded with invented content.
- Added learner-specific question sessions and exposure tracking, unseen-first selection, adaptive difficulty and prerequisite focus, server-side grading, post-answer source feedback, learner reports, and teacher review/delete routes.
- Removed automatic Mathematics enrollment for new learners and moved the bundled Mathematics, Physics, and Python packs under `content/examples/`, available through an explicit sample-subject option.
- Added migration `0006_rule_based_quizzes`, saved-source tests, adaptive quiz API coverage, and updated quiz/onboarding documentation. RL remains trained and evaluated only with simulated data.

### Phase G — subject enrollment and internet discovery

- Added required 1–8 subject selection after learner profile setup, with installed packs, manual subjects, public search, path preview, removable chips, and later dashboard management.
- Added an eight-active-enrollment server limit, target depth and education-level capture, manual subject enrichment, and reference-book metadata.
- Added bounded public-source discovery for Wikipedia/Wikidata, Open Library, and OpenAlex, with HTTPS allowlists, DNS checks, response limits, timeouts, caching, and per-user process-local request limits.
- Added ordered, prerequisite-linked draft topics and cited resources with source/retrieval provenance. Drafts are explicitly unreviewed; no LLM or question generation was added.
- Added honest "No quiz yet" states, optional 0–5 self-ratings, and data-backed weakness/improvement summaries.
- Added migration `0005_subject_discovery`, mocked provider and enrollment/discovery tests, and a Playwright onboarding check.

### Phase F — final cleanup and local release

- Added a local Makefile workflow for setup, training, migration, running, tests, lint, and cache cleanup.
- Completed the approved cleanup: removed the duplicate server requirements file and unused `python-multipart` manifest entry; kept generated data, model, plot, and report artifacts tracked.
- Added README charts generated from checked-in simulator reports, validation measurements, and the latest pytest coverage data.
- Refreshed screenshot capture for the current onboarding flow and added an onboarding screenshot.
- Improved accessible labels and landmarks, responsive layout, and explicit recommender initialization errors.
- Documented measured load limits, the remaining broad mypy diagnostics, and the upstream SlowAPI/SQLite warnings.

### Phase S — project state and stabilization

- Added the project handoff state and agent instructions.
- Added recommendation recency and topic coverage adjustments, responsive layout fixes, clearer error messages, an interaction-history index, and SQLite pool tuning based on local profiling.
- Regenerated the current generalized model artifacts; the validated app mode is reported by `/ready`.
- High 100-user latency and some recommendation repetition remain open. No real learning gains are established.

### Phase M — multi-subject platform

- Added subjects, ordered topics, prerequisite edges, resources, questions, and enrollments as database-backed content.
- Scoped learner progress and interactions by subject and added an Alembic migration that carries legacy Mathematics state forward.
- Added validated JSON content packs and an import CLI; included Mathematics, Python Programming, and Physics packs with six topics and eight draft questions per topic.
- Added subject enrollment/switching, diagnostic, per-subject progress, prerequisite-filtered recommendations, quiz submission, history, and teacher content APIs.
- Added teacher-role gates for content writes, subject selection, a topic map, diagnostic UI, and visible recommendation rationale.
- Generalized simulator feature rows and Q state/action encoding, added multiple random prerequisite graphs and a coverage term, and expanded evaluation report generation with simulated group gaps.
- Updated project, architecture, API, data, security, and contribution documentation, plus assignment-to-files mapping.
- Updated the screenshot helper to import its pack and capture the diagnostic flow in its temporary database.

### Known follow-up

- The generalized pipeline was trained and evaluated successfully in an isolated temporary copy. Those generated artifacts were not copied into this checkout; its legacy artifacts remain incompatible, so the app uses its ZPD fallback until the local training command is run.
- Teacher self-registration is public and is not safe for a shared deployment.
- The generated reports contain one isolated simulated run; checked-in CSV/model artifacts have not been regenerated for the new schema.
- Content questions are drafts and still need teacher review. Synthetic evaluation does not establish real learning gains.

## [Phase 4.5] - 2026-10-10

### Added

- Functional, recommendation, robustness, security, and browser validation tests and a validation report.

## [Phase 4] - 2026-10-10

### Added

- Beginner-friendly setup and limitation notes in `README.md`.
- Architecture, API, data dictionary, security, and contribution guides.
- A Playwright screenshot helper and capture instructions for sign-in, dashboard, and quiz screens.
- A summary of completed and open findings in `PROJECT_REPORT.md`.

## [Phase 3] - 2026-10-10

### Added

- Pytest API, service, and browser-flow tests using temporary SQLite databases.
- Ruff lint/format, mypy, pre-commit configuration, and coverage enforcement.
- JSON request logs with request IDs and timing, plus `/health` and `/ready` endpoints.

## [Phase 2] - 2026-10-10

### Added

- Environment-based application settings and production validation for the signing secret.
- Password length/content checks, login and registration rate limits, refresh-token rotation and revocation, and duplicate-username handling.
- Security headers, configured CORS, SQLite foreign-key enforcement, an Alembic migration, and account deletion.

## [Phase 1] - 2026-10-10

### Added

- Server-side quiz grading, answer submission, and activity-duration limits.
- Local Chart.js asset and pinned runtime dependency manifests.

### Fixed

- Quiz submit-button ID mismatch.
- Auth-route module placement and listed dead code in the training scripts.
