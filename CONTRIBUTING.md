# Contributing

Thanks for helping improve the project. Keep changes small and describe them in plain language. Do not add real learner data, secrets, database files, virtual environments, or generated model outputs to commits.

## Development setup

From the repository root:

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -r requirements.txt -r requirements-dev.txt
cp .env.example .env
playwright install chromium
python run_all.py
alembic upgrade head
python -m app.content import content/mathematics
python -m app.content import content/python-programming
python -m app.content import content/physics
```

Replace the example `APP_SECRET` with a private random value before creating accounts you care about. For example, run `python -c 'import secrets; print(secrets.token_urlsafe(48))'` and put the result in `.env`. Keep the value stable while using the same database. Tests use their own temporary database and test secret; they must not access `outputs/app.db`.

`python run_all.py` overwrites generated CSVs, model artifacts, plots, and reports under `outputs/`; back up any generated work you need to preserve first. The pack import commands populate the default local database. Do not import packs into a database containing important data without making a backup.

## Branches and commits

- Make a short branch for one change, for example `docs/api-guide` or `fix/quiz-grading`.
- Use a short imperative commit subject, optionally with a clear area prefix, such as `docs: describe refresh-token flow` or `fix: validate quiz answer count`.
- Do not include generated files from `outputs/` unless a change explicitly requires a reviewed model artifact.
- Explain user-visible changes and checks in the pull request description.

## Checks

Run relevant checks before opening a pull request:

```bash
pytest
ruff check .
ruff format --check .
mypy
pre-commit run --all-files
```

The browser test needs Chromium from Playwright. It exercises a complete account and quiz flow using a temporary server/database.

## Adding a subject or topic

Subjects and topics are content, not application constants. To add or revise content:

1. Create or update `content/<subject>/content.json` using the existing packs as examples. Include a unique subject ID, ordered topics, prerequisites, resources, and questions.
2. Mark question status honestly. Included questions are drafts and need teacher review.
3. Give every topic a diagnostic question if new enrollments need a diagnostic; each diagnostic must have valid answer options and a server-side correct option.
4. Validate/import the pack into a temporary database first with `python -m app.content import content/<subject>`. Import is idempotent for matching IDs; review the pack carefully because import updates matching content.
5. Add tests for pack validation/import and subject enrollment, prerequisites, public question redaction, and server-side grading.
6. Update [docs/API.md](docs/API.md) and [docs/DATA_DICTIONARY.md](docs/DATA_DICTIONARY.md) if the API or stored shape changes.

Do not add subject-specific topic IDs to model code. The model feature schema describes a candidate topic and its prerequisites rather than a fixed subject or topic identity.

Do not reuse an existing topic index for another topic because saved history and model features depend on the topic order.

## Adding an API route

1. Put the route in the matching module under `app/routes/`; place shared business logic under `app/services/` when appropriate.
2. Use Pydantic schemas for request validation and `current_user` for learner-specific protected data.
3. Use `current_user` and explicitly require the `teacher` role for content writes. Do not assume the current public teacher self-registration is suitable for a deployed product.
4. Use SQLAlchemy models instead of building SQL from user text. Do not log passwords, tokens, answer selections, or request bodies.
5. Add API tests with the fixtures in `tests/conftest.py`. Use the temporary test database, not `outputs/app.db`.
6. Add the endpoint to `docs/API.md`, including auth needs, request/response fields, errors, and a curl example.
7. Run the checks listed above. If the schema changes, add an Alembic migration and explain how it affects existing databases.