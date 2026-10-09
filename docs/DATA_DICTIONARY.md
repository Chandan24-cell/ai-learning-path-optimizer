# Data dictionary

This document describes the SQLAlchemy schema, generated CSV/NumPy files, and model artifacts. Synthetic learner and interaction data is not real learner evidence. The database may contain sensitive account and activity data; never publish it.

## Database tables

The ORM is defined in [app/models_db.py](../app/models_db.py); schema changes are in `migrations/versions/`. Column types below are SQLAlchemy declarations as represented by SQLite. Application/ORM defaults are not necessarily database server defaults. No check constraints are declared unless stated.

### `users`

| Column | Type | Constraints/default | Meaning |
|---|---|---|---|
| `id` | Integer | Primary key | Internal user identifier. |
| `username` | String(64) | Not null, unique, indexed | Normalized login name. API accepts 3–32 ASCII letters, digits, or underscores. |
| `hashed_password` | String(255) | Not null | bcrypt hash. A raw password is not stored. |
| `role` | String(16) | Not null; ORM default `student` | Application role: `student` or `teacher`. Teacher self-registration is currently allowed. |
| `active_subject_id` | String(80) | Nullable; no foreign key | Current UI subject selection. Routes check subject enrollment before switching. |
| `created_at` | DateTime | Server default current time | Account creation time. |

### `learner_profiles`

One profile per student. The migration does not create profiles for existing accounts; those students complete onboarding at their next sign-in.

| Column | Type | Constraints/default | Meaning |
|---|---|---|---|
| `user_id` | Integer | Primary key; foreign key to `users.id`, cascade delete | Profile owner. |
| `country` | String(120) | Not null | Selected country option ID, such as `IN`. |
| `language` | String(80) | Not null | Selected preferred language. |
| `education_level` | String(40) | Not null | Selected education-level key. |
| `institution_type` | String(40) | Not null | Category only; no institution name is collected. |
| `grade_year` | String(80) | Not null | Student-entered class, grade, or year. |
| `curriculum_program` | String(120) | Nullable | Optional country curriculum or program choice. |
| `field_of_study` | String(120) | Not null | Student-entered field of study. |
| `learning_goal` | String(24) | Not null | One of exam, skill, career, curiosity. |
| `weekly_time_hours` | Float | Not null; API range 0.5–80 | Learner's estimate of available weekly study time. |
| `learning_style` | String(24) | Not null | Preferred text, visual, examples, or mixed style. |
| `prior_experience` | String(24) | Not null | Self-reported experience category. |
| `consent_version` | String(32) | Not null | Version of the privacy notice accepted by the learner. |
| `consent_at` | DateTime | Not null | Time the learner accepted the current notice. |
| `updated_at` | DateTime | Nullable; server default current time | Last update time, when populated by the ORM. |

Countries, curricula, education-level mappings, languages, and the visible privacy notice are stored in `content/learner-profile/options.json`. The app does not collect age or date of birth. The under-18/unknown-age notice recommends discussing consent with a trusted adult but does not verify guardian consent.

### `subjects`

| Column | Type | Constraints/default | Meaning |
|---|---|---|---|
| `id` | String(80) | Primary key | Stable pack/subject identifier, such as `mathematics`. |
| `name` | String(120) | Not null, unique | Display name. |
| `description` | Text | Not null; ORM default empty string | Short subject description. |
| `questions_status` | String(80) | Not null; ORM default `draft; teacher review required` | Content-review warning shown to users. |
| `source` | String(16) | Not null; `pack`, `manual`, or `discovered` | How the subject was created. Enriched manual subjects remain `manual`. |
| `status` | String(16) | Not null; `draft` or `reviewed` | Review state. Public-source paths remain drafts until reviewed. |
| `created_by` | Integer | Nullable | Owner ID for personal manual/discovered subjects. |
| `source_url` | Text | Nullable | Approved public source used to create/enrich a subject. |
| `retrieved_at` | DateTime | Nullable | Retrieval time for the source record. |
| `reference_book` | Text | Nullable | Optional serialized reference metadata; contains bibliographic fields and a link, not book text. |

### `topics`

| Column | Type | Constraints/default | Meaning |
|---|---|---|---|
| `id` | String(160) | Primary key | Stable ID, usually `<subject-id>.<slug>`. |
| `subject_id` | String(80) | Not null; foreign key to `subjects.id`; indexed | Owning subject. |
| `slug` | String(80) | Not null | URL/pack-friendly topic key. |
| `name` | String(160) | Not null | Display name. |
| `order` | Integer | Not null | Display and diagnostic ordering. |
| `source_url` | Text | Nullable | Source citation for a discovered topic. |
| `retrieved_at` | DateTime | Nullable | When the topic outline was retrieved. |
| `provenance` | Text | Nullable | JSON metadata identifying source/provider and outline location. |
| `source_extract` | Text | Nullable | Sanitized, short cited source extract used as input to rule-based question generation. |
| `quiz_status` | String(24) | Not null; default `not_generated` | Lazy-generation state: `not_generated`, `ready`, or `limited`. |

### `topic_prerequisites`

| Column | Type | Constraints/default | Meaning |
|---|---|---|---|
| `topic_id` | String(160) | Composite primary key; foreign key to `topics.id` | Topic that depends on another topic. |
| `prerequisite_topic_id` | String(160) | Composite primary key; foreign key to `topics.id` | Required topic. The API and pack validator require same-subject edges and reject cycles. |

The composite primary key prevents duplicate directed edges. The schema itself does not enforce same-subject membership or acyclicity.

### `resources`

| Column | Type | Constraints/default | Meaning |
|---|---|---|---|
| `id` | String(180) | Primary key | Resource ID, usually `<topic-id>.<slug>`. |
| `topic_id` | String(160) | Not null; foreign key to `topics.id`; indexed | Topic this activity belongs to. |
| `type` | String(40) | Not null | Label: `video`, `article`, `quiz`, `interactive`, or `project`; this does not mean a hosted resource exists. |
| `title` | String(200) | Not null | Display label. |
| `difficulty` | Float | Not null | Resource difficulty, API range 1–5. |
| `duration` | Float | Not null | Expected duration in minutes. |
| `url` | Text | Nullable | Optional resource URL. |
| `body` | Text | Nullable | Optional text description/content. |
| `source_url` | Text | Nullable | Source citation for a discovered resource reference. |
| `retrieved_at` | DateTime | Nullable | When the resource link was collected. |
| `provenance` | Text | Nullable | JSON metadata about provider and source. |

### `questions`

| Column | Type | Constraints/default | Meaning |
|---|---|---|---|
| `id` | String(180) | Primary key | Question ID. |
| `topic_id` | String(160) | Not null; foreign key to `topics.id`; indexed | Topic assessed by the question. |
| `difficulty` | Float | Not null | Question difficulty; API range 1–5. |
| `text` | Text | Not null | Prompt text. |
| `options_json` | Text | Not null | JSON array of answer-choice strings. |
| `correct_option` | Integer | Not null | Zero-based server-side answer index. Not included in public question responses. |
| `explanation` | Text | Not null | Feedback shown after grading. |
| `diagnostic` | Boolean | Not null; ORM default false | Whether the question is selected for the enrollment diagnostic. |
| `question_type` | String(32) | Nullable | Rule-based type: definition-to-term, cloze, Wikidata fact, or true/false. |
| `source_sentence` | Text | Nullable | Short source sentence supporting a generated question and its explanation. |
| `source_url` | Text | Nullable | Link to the Wikipedia/Wikidata source. |
| `attribution` | String(160) | Nullable | Required source attribution, including Wikipedia CC BY-SA or Wikidata CC0. |
| `generated_at` | DateTime | Nullable | Generation time for generated questions. |
| `generator_version` | String(40) | Nullable | Rule-generator version used to build the item. |
| `status` | String(80) | Nullable | Review state; generated questions are marked auto-generated and unreviewed. |

The database does not declare a range constraint on `correct_option`; API validation checks that it points into the options list. The answer key and explanation are server-side and are not returned before grading. Existing pack questions may have no public-source citation; rule-generated items are only built from saved cited material.

### `question_sessions`

One record represents a diagnostic or adaptive activity session for a single learner and subject.

| Column | Meaning |
|---|---|
| `id` | Session identifier. |
| `user_id`, `subject_id`, `topic_id` | Learner, subject, and starting topic. |
| `resource_id`, `mode` | Activity/resource context and `diagnostic` or `activity` mode. |
| `max_questions`, `asked_count`, `correct_count` | Session question limit and counts. |
| `reused_questions`, `prerequisite_focus` | Whether the bank had to reuse seen material and whether the next question targets a weak prerequisite. |
| `started_at`, `completed_at` | Session lifecycle timestamps. |

### `question_exposures`

One row tracks a question shown to a learner within a session. A unique `(session_id, question_id)` constraint prevents repeats within that session. User/subject/question IDs, seen time, optional answer index, correctness, and answered time support unseen-first selection and adaptive behavior. Grading is performed on the server.

### `question_reports`

Learner reports on shown questions include reporter, question, reason, optional sanitized details, status (`open`, `reviewed`, or `dismissed`), creation time, and optional teacher reviewer/time. Deleting a question cascades its exposure and report records.

### `enrollments`

| Column | Type | Constraints/default | Meaning |
|---|---|---|---|
| `user_id` | Integer | Composite primary key; foreign key to `users.id` | Enrolled learner. |
| `subject_id` | String(80) | Composite primary key; foreign key to `subjects.id` | Enrolled subject. |
| `created_at` | DateTime | Server default current time | Enrollment creation time. |
| `diagnostic_completed` | Boolean | Not null; ORM default false | Whether the one-time diagnostic has been submitted. |
| `education_level_used` | String(40) | Nullable | Profile education level captured when the enrollment was created. |
| `target_depth` | String(16) | Not null; ORM default `beginner` | Learner's intended path depth: beginner, intermediate, or advanced. |
| `reference_book` | Text | Nullable | Optional serialized bibliographic metadata and source link. |

### `student_states`

There is one record per `(user_id, subject_id)`. Mastery and attempts are JSON text maps keyed by topic IDs.

| Column | Type | Constraints/default | Meaning |
|---|---|---|---|
| `user_id` | Integer | Composite primary key; foreign key to `users.id` | Learner. |
| `subject_id` | String(80) | Composite primary key; foreign key to `subjects.id` | Subject whose progress is stored. |
| `ability` | Float | Nullable; ORM default `0.0` | Score-derived internal estimate. |
| `motivation` | Float | Nullable; ORM default `0.6` | Internal profile value; not a measured psychological trait. |
| `learner_level` | Float | Not null; default `25.0` | Estimated learner level from 0 to 100, initialized from education level and adjusted by diagnostic performance. |
| `learner_level_label` | String(40) | Not null; default `middle_school` | Education-level label associated with the numerical level. |
| `learning_goal` | String(24) | Not null; default `skill` | Goal feature copied from the current learner profile. |
| `mastery_est_json` | Text | Nullable; ORM default `{}` | JSON object mapping topic IDs to mastery estimates. New enrollments start at 0.25 before diagnostic. |
| `attempts_json` | Text | Nullable; ORM default `{}` | JSON object mapping topic IDs to activity attempt counts. |
| `recent_scores_json` | Text | Nullable; ORM default `[]` | JSON array of the most recent score values; runtime keeps at most five. |
| `self_ratings_json` | Text | Nullable; ORM default `{}` | Topic-keyed 0–5 self-reports. These are weak signals, not quiz scores. |
| `total_time_min` | Float | Nullable; ORM default `0.0` | Sum of submitted client-reported activity duration. |
| `engagement_ma` | Float | Nullable; ORM default `0.5` | Moving average of estimated engagement. |
| `last_difficulty` | Float | Nullable; ORM default `3.0` | Difficulty of the latest activity. |
| `last_score` | Float | Nullable; ORM default `50.0` | Latest server-calculated score. |
| `n_interactions` | Integer | Nullable; ORM default `0` | Number of submitted activities for this subject. |

### `interactions`

One row records one submitted resource quiz. Most fields are nullable in the schema; the API supplies them on successful submissions.

| Column | Type | Constraints/default | Meaning |
|---|---|---|---|
| `id` | Integer | Primary key | Interaction ID. |
| `user_id` | Integer | Nullable; foreign key to `users.id`; indexed | Learner who submitted it. |
| `subject_id` | String(80) | Not null; foreign key to `subjects.id`; ORM default `mathematics` | Subject context. |
| `timestamp` | DateTime | Nullable; server default current time | Creation time. |
| `action` | Integer | Nullable | Legacy catalogue position where supplied; subject-specific API submissions may leave this empty. |
| `resource_id` | String(180) | Nullable, no foreign key | Resource identifier at submission time. |
| `topic` | String(160) | Nullable | Topic ID at submission time. |
| `rtype` | String(32) | Nullable | Resource type label at submission time. |
| `difficulty` | Float | Nullable | Resource difficulty at submission time. |
| `duration` | Float | Nullable | Client-reported duration in minutes. |
| `score` | Float | Nullable | Server-calculated score from 0 to 100. |
| `gain` | Float | Nullable | Estimated mastery change from the app's update rule. |
| `engagement` | Float | Nullable | Estimated engagement, not a measured learning outcome. |

### `refresh_tokens`

| Column | Type | Constraints/default | Meaning |
|---|---|---|---|
| `id` | String(128) | Primary key | JWT token ID (`jti`) used to look up and revoke a refresh token. |
| `user_id` | Integer | Not null; foreign key to `users.id`; indexed | Token owner. |
| `expires_at` | DateTime | Not null | Stored expiration time. |
| `revoked` | Boolean | Not null; ORM default false | Whether the token has been rotated or revoked. |

### `alembic_version`

Alembic-managed table with `version_num` (`VARCHAR(32)`, primary key, not null), containing the latest applied migration revision.

## Content-pack data

Each `content/<subject>/content.json` has a `subject` object with ID, name, description, and question-review status, plus arrays for topics, prerequisite IDs, resources, and questions. Question `options` are strings; `correct_option` is a zero-based index; `diagnostic` marks the one question selected for initial subject assessment. Pack validation checks required keys, types, IDs, references, option ranges, and prerequisite graph validity. Packs are source content, not CSVs under `outputs/data/`.

## Generated CSV and NumPy files

The checked-in CSVs use the generalized, subject-agnostic simulator schema. Rows describe simulated learners, resources, and outcomes; they are not real learner data. CSV types are inferred by pandas on load. `python run_all.py` regenerates these files and the model artifacts.

### `outputs/data/catalog.csv`

Current checked-in columns:

| Column | Meaning |
|---|---|
| `resource_id` | Synthetic candidate resource identifier. |
| `topic_id` | Candidate topic identifier in a generated graph. |
| `topic` | Synthetic topic index within the graph. |
| `topic_name` | Generated topic label, not a real subject title. |
| `rtype` | Resource-type label; it does not identify a real hosted resource. |
| `difficulty` | Synthetic resource difficulty. |
| `duration` | Simulated expected duration in minutes. |
| `learning_power` | Simulator parameter controlling synthetic mastery gain. |
| `engagement_prior` | Simulator parameter controlling synthetic engagement. |
| `prerequisites` | Serialized prerequisite IDs for the candidate topic. |
| `graph_id` | Generated topic-graph identifier. |

### `outputs/data/students.csv`

Current checked-in columns:

| Column | Meaning |
|---|---|
| `student_id` | Synthetic learner number. |
| `graph_id` | Generated subject-graph identifier. |
| `ability` | Generated latent simulator parameter. |
| `motivation` | Generated simulator parameter between 0 and 1. |
| `learner_level` | Generated synthetic education/learner level between 0 and 100. |
| `learner_level_label` | Simulated primary-to-professional level category. |
| `learning_goal` | Simulated exam, skill, career, or curiosity goal. |
| `group` | Generated `high-ability` or `low-ability` evaluation group. |
| `level_group` | Generated `high-level` or `low-level` evaluation group. |
| `mean_prior_mastery` | Mean simulated starting mastery across the learner's generated topic graph. |

### `outputs/data/interactions.csv`

Columns:

| Column | Meaning |
|---|---|
| `candidate_topic_mastery` | Simulated mastery estimate for the candidate topic before the activity. |
| `prerequisite_mastery_average` | Mean simulated mastery of prerequisite topics. |
| `difficulty_gap` | Difference between learner level for the candidate and resource difficulty. |
| `engagement` | Estimated engagement before the activity. |
| `recent_score_trend` | Recent simulated score trend. |
| `attempts` | Prior attempts on the candidate topic. |
| `resource_type` | Resource-type label such as `video` or `quiz`; not a hosted resource. |
| `time` | Cumulative simulated learning time. |
| `learner_level` | Simulated learner level, scaled for model input. |
| `learning_goal` | Simulated learning goal label. |
| `student_id` | Synthetic learner ID. |
| `graph_id` | Generated topic-graph ID. |
| `action` | Abstract action index for the resource-type/difficulty-step pair. |
| `score` | Simulated next assessment score from 0 to 100. |
| `gain` | Simulated underlying mastery gain. |
| `engagement_outcome` | Simulated engagement outcome from 0 to 1. |

### `outputs/data/processed.npz`

NumPy archive written by preprocessing. It contains:

- `X_train`, `y_train`; `X_val`, `y_val`; `X_test`, `y_test` — transformed features and score targets.
- `train_ids`, `val_ids`, `test_ids` — synthetic graph or learner identifiers associated with each split.

Dimensions can change with regenerated graphs, feature selection, or pipeline settings. The current source separates generated topic graphs between data splits.

## Model artifacts

| Path | Contents | Written/loaded by |
|---|---|---|
| `outputs/models/pipeline.joblib` | Fitted input preprocessing pipeline | Written by `src/task2_preprocessing.py`; loaded by the predictor code. |
| `outputs/models/q_table.json` | Validated JSON mapping abstract Q states to action values | Written by `src/task4_qlearning.py`; loaded by `app/services/recommender.py` and offline evaluation. |
| `outputs/models/predictor/pipeline.joblib` | Predictor's fitted feature pipeline | Written and loaded by `src/task3_model.py`. |
| `outputs/models/predictor/score_model.keras` | TensorFlow score predictor when that backend was used | Written/loaded by `src/task3_model.py`. |
| `outputs/models/predictor/score_model.joblib` | scikit-learn fallback predictor when TensorFlow was unavailable | Written/loaded by `src/task3_model.py`. |
| `outputs/models/predictor/meta.json` | Predictor metadata and backend information | Written/read by `src/task3_model.py`. |

The checked-in predictor metadata and Q table match the current generalized feature schema; `/ready` reports the active mode and currently reports `hybrid`. Treat joblib and Keras files as trusted executable artifacts, and use only files from a trusted build.

Generated plots are in `outputs/plots/`; the seven Task reports are in `outputs/reports/`. `python run_all.py` regenerates these along with the CSVs and model files. Back them up first if they need to be preserved.
