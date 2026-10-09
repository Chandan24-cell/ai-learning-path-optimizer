# Security notes

This section explains the protections currently in the code and what still needs attention before a public deployment. It is a guide to the current implementation, not a guarantee that the app is safe for real student data.

## Protections in place

- **Passwords:** the app stores bcrypt hashes, not plaintext. Registration requires at least 10 characters, rejects all-digit and a small list of common passwords, and rejects passwords over bcrypt's 72-byte UTF-8 limit.
- **Usernames:** input is trimmed and lowercased, then restricted to 3–32 ASCII letters, numbers, and underscores.
- **Tokens:** access tokens last 15 minutes by default. Refresh tokens last 7 days, have a separate token type, and store a token ID in the database. Refresh rotates and revokes the old token; logout revokes the supplied refresh token.
- **Authentication and deletion abuse:** registration, login, and account deletion are limited to five attempts per minute per IP using SlowAPI. Limits are in process memory; they are not shared across multiple workers or servers.
- **Duplicate registration:** a uniqueness conflict is rolled back and returned as HTTP 409.
- **Browser headers:** responses include a same-origin Content Security Policy, `X-Content-Type-Options`, `X-Frame-Options`, and `Referrer-Policy`.
- **CORS:** the app permits only origins listed in `ALLOWED_ORIGINS`. An empty setting permits no cross-origin browser origins.
- **Input and grading:** Pydantic checks request fields. Quiz answers are graded by the server; the client cannot send a score. Activity duration is client-reported but limited to 0.5–120 minutes.
- **Learner profile and privacy:** student onboarding asks only for country, language, education level, institution type, grade/year, optional curriculum/program, field of study, learning goal, weekly study time, preferred learning style, and prior experience. It does not ask for age, birth date, full name, or institution name. Choices and curriculum lists are loaded from `content/learner-profile/options.json`. Student learner routes require a saved profile; profile editing and deletion are available.
- **Consent and minors:** the onboarding screen explains collection and purpose and requires an affirmative checkbox. It says users under 18 or whose age is unknown should review the notice with a trusted adult. Age is not collected, and the app does not verify age or guardian consent. The checkbox is not a substitute for jurisdiction-specific consent, school, or child-privacy review.
- **Database:** SQLite foreign keys are enabled per connection. Alembic manages the schema. Account deletion asks for the current password and removes the account's profile, state, interactions, enrollments, and refresh tokens. Profile deletion removes the profile and resets level/goal values, after which student learning routes require onboarding again.
- **Logging:** request logs include request ID, method, path, status, and duration. They do not include request bodies, passwords, tokens, or selected answers.
- **Browser rendering:** dynamic server values are inserted using text nodes and `textContent` rather than HTML parsing.
- **Internet discovery:** provider requests are limited to exact approved HTTPS hosts. The fetcher rejects credentials, redirects, proxy environment settings, non-public DNS answers, unexpected content types, oversized responses, and slow requests; responses are cached briefly. Discovery result strings are untrusted data and the UI inserts them with `textContent`.
- **Discovery abuse limits:** search and books endpoints use a per-user, in-memory limit. It is not shared across workers and resets when the process restarts.
- **Enrollment cap:** the API rejects a ninth active subject and unenrolling frees a slot. The current lock is process-local; it does not provide a cross-process/database-level invariant if the app is run with multiple workers.
- **Public-source content:** summaries are short and links are retained instead of book/page text. Discovered topic paths are unreviewed drafts. Source content may be incorrect, maliciously authored, unavailable, or unsuitable for a learner; review it before treating it as curriculum.
- **Rule-based quiz content:** generation uses only short source extracts already stored for a topic and structured Wikidata facts. Text is normalized and length-capped, filtered for sentence and option quality, stored with source URL and attribution, and marked unreviewed. These checks do not prove factual correctness or suitability.
- **Quiz answer privacy:** correct options and explanations remain server-side until an authenticated learner answers an exposed question. Sessions and question exposures are associated with the learner. Learner reports require enrollment and evidence the question was shown; teacher report/review endpoints require the teacher role.

## Important limits

- Tokens are stored in browser `localStorage`. A future cross-site scripting bug could expose them. A secure, HTTP-only cookie design would need CSRF protections and a different frontend flow.
- The token signing secret must be private and stable across production restarts. Production refuses to start if `APP_SECRET` is missing, shorter than 32 characters, or the former development default. Development without a configured secret uses a random key that changes when the process restarts.
- SlowAPI currently emits deprecation warnings in the installed environment about `asyncio.iscoroutinefunction`; this comes from the dependency and should be revisited when updating SlowAPI/Python.
- Rate limits use process memory and client IP detection. They do not provide a distributed limit and can be affected by reverse-proxy configuration.
- SQLite is convenient locally, but is not configured or load-tested for a high-write multi-instance service. No PostgreSQL production setup is included yet.
- The app has a `student`/`teacher` role field and teacher-only content-write routes, but registration is public and accepts `role:"teacher"`. Anyone can therefore self-register as a teacher and modify shared subject content. This is a known deployment blocker until teacher provisioning is restricted. There is no account recovery, email verification, or audit history.
- There is no central token revocation for already-issued access tokens. Logout revokes refresh capability; an unexpired access token remains valid until expiry.
- Duration is supplied by the browser and range-checked, not measured by a trusted server clock.
- Q-table artifacts use validated JSON and cannot execute code during deserialization. Predictor files still use joblib/Keras formats; only load artifacts that you generated or otherwise trust.
- Training and evaluation use synthetic people and simulated outcomes. Do not use these results to make consequential decisions about real learners.
- Generated questions are recall-style and are not expert assessment. Sparse source material may result in a limited quiz or no quiz; self-ratings remain weak signals and are not counted as quiz answers.
- Country, language, education level, field of study, goal, time availability, learning style, and prior experience are personal profile data. The level is an estimate initialized from self-report and adjusted by a short diagnostic; it is not a credential or objectively validated assessment. Keep access restricted and establish retention/deletion practices before collecting real student information.
- The current code has no TLS configuration. Use HTTPS at the hosting platform or a trusted reverse proxy.

## Database migration safety

The first migration supports the original single-subject tables. The subject-platform migration adds content and enrollment tables, changes learner state to `(user_id, subject_id)`, and copies the previous Mathematics learner state into the Mathematics subject record. The learner-profile migration adds onboarding fields and subject levels; existing accounts receive no invented profile and must complete onboarding. Validate migrations against a fresh temporary database. Before migrating a real local database, make an access-controlled backup:

```bash
cp outputs/app.db "outputs/app.db.backup-$(date +%Y%m%d-%H%M%S)"
alembic upgrade head
```

Keep the backup somewhere access-controlled because it may contain password hashes and learning history. Never commit or share the database file.

The subject-discovery migration adds subject source/review metadata, topic/resource provenance, enrollment depth/reference fields, and learner self-rating storage. Migration `0006_rule_based_quizzes` adds source extracts, generated-question provenance, learner question sessions/exposures, and question reports. Test migrations only against a temporary database or a copy of the pre-migration backup; do not point migration validation at `outputs/app.db`. The checked-in model and Q-table remain simulation-trained.

## Before deploying

- [ ] Set `APP_ENV=production` and a private, randomly generated `APP_SECRET` with at least 32 characters.
- [ ] Set `DATABASE_URL` to a managed database and confirm that the selected SQLAlchemy driver is installed and tested; PostgreSQL deployment is not supplied in this phase.
- [ ] Set `ALLOWED_ORIGINS` to only the real website origins.
- [ ] Use HTTPS and configure trusted proxy headers correctly.
- [ ] Back up the database, apply migrations, and test restore procedures.
- [ ] Keep generated models and dependencies from trusted build sources; protect them from untrusted writes.
- [ ] Review account deletion, privacy notices, consent, data retention, and access rights for the intended users.
- [ ] Obtain qualified privacy/legal review for intended countries and age groups. Do not treat the app's notice or consent checkbox as verified guardian consent or regulatory compliance.
- [ ] Replace public teacher self-registration with a trusted provisioning process; review and audit all teacher content changes.
- [ ] Add monitoring, a shared rate-limit store, operational alerting, and load tests for the actual deployment.
- [ ] Run the API and browser test suites and review outstanding type-checking and dependency warnings.
- [ ] Do not treat synthetic evaluation scores as evidence of real-world educational benefit.
