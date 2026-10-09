# Deploy on Render

This guide builds the app as a Docker image and stores production data in
Render PostgreSQL. The app does **not train models at startup**. Its image
contains a small NumPy export of the saved predictor and the Q table.

## Before you begin

- Create a Render account and install Docker Desktop (needed to test locally).
- Keep this repository private if it contains data you do not want public.
- Do not copy `.env`, database files, backups, or credentials into the image.
- Treat this app as a prototype, not a validated product for real student data.
  Teacher self-registration is still open, rate limits are process-local, and
  consent/privacy and education outcomes have not had a legal or field review.

## Test with Docker Compose

1. Make a private `.env` file at the repository root (it is git-ignored) with
   a random secret of at least 32 characters:

   ```dotenv
   APP_SECRET=replace-with-a-long-random-private-value
   ```

2. Start the app and PostgreSQL:

   ```sh
   docker compose up --build
   ```

   Compose applies Alembic migrations to its named `postgres_data` volume before
   starting the web server. The local-only sample credentials in Compose are
   not production credentials. Open <http://localhost:8000>, register a student,
   choose a sample subject, complete onboarding, then start a quiz.

3. Check the image size and that the process is non-root:

   ```sh
   docker image ls ai-learning-path-optimizer-app
   docker compose exec app id
   docker compose exec app python -c "import os; print('uid=', os.getuid())"
   ```

   `uid` must not be `0`. The Compose tag can be found with `docker compose
   images` if Docker assigns a different name.

4. Run the PostgreSQL migration integration test against the dedicated,
   disposable `learning_path_test` database created by the Compose init script:

   ```sh
   TEST_POSTGRES_URL=postgresql+psycopg://learning_path:local-compose-only-password@localhost:54329/learning_path_test \
     .venv/bin/python -m pytest tests/test_postgres_migrations.py -q
   ```

   This test refuses any database not named `learning_path_test`. Do not point
   it at production or at `outputs/app.db`.

5. Stop the stack:

   ```sh
   docker compose down
   ```

   To remove the local PostgreSQL data too, explicitly remove the
   `postgres_data` volume with Docker; do not do this if you need the test data.

## Deploy with the Render Blueprint

1. In Render, create a new Blueprint from this repository and review
   `render.yaml`. It creates a Docker web service and a managed PostgreSQL
   database. Render generates `APP_SECRET` privately and supplies the internal
   PostgreSQL connection string.
2. Confirm the PostgreSQL plan, region, backups, and cost in Render before
   creating resources. Set the service's `ALLOWED_ORIGINS` to the exact HTTPS
   origin where the site will be opened. The checked-in value uses the default
   Render hostname; update it if the service name or custom domain differs.
3. Deploy. Render runs `alembic upgrade head` as the pre-deploy command. The
   web server starts only if deployment succeeds, then Render checks `/ready`.
   Do not also run migrations from multiple web workers.
4. Verify `/health` is HTTP 200 and `/ready` reports `database: ok` and the
   recommender mode. `/health` checks that the process responds; `/ready` also
   needs a reachable database. The recommender reports `zpd-fallback` if its
   optional serving assets are absent. `/docs` is unavailable in production.
   Test registration, login, onboarding, and a quiz before sharing the URL.
5. Use Render's HTTPS endpoint and its forwarded protocol/client headers. The
   container trusts forwarded headers because it is intended to be reachable
   only through Render's proxy; do not expose the container directly to an
   untrusted network. HSTS is emitted in production.

For a custom domain, update both `ALLOWED_ORIGINS` and the Render domain/TLS
settings. Never put a secret in `render.yaml`, a Docker build argument, source
control, screenshots, or logs.

## Models, image size, and memory

The checked-in TensorFlow `.keras` predictor occupies about **856 KiB** and the
Q table about **12 KiB**. TensorFlow's installed Python package occupied about
**1.2 GiB** in the development environment (that is package-directory size,
not a Docker image measurement). The serving artifact is about **255 KiB** and
uses NumPy dense-layer inference; the runtime requirements omit TensorFlow,
scikit-learn, SciPy, and training packages. The Docker build context includes
only `q_table.json` and the optional NumPy serving exports from `outputs/models/`.
If the exports are unavailable, the app starts in its documented ZPD fallback
mode instead of failing during image construction.

Previous local load testing measured a peak of approximately **561 MiB RSS**
with the TensorFlow serving setup and a first model-using initialization of
about **8.3 seconds**. The reduced runtime avoids that TensorFlow import. An
exact final image size and container RSS depend on the local Docker build and
Render instance. Expect a Python, NumPy, and
pandas image in the several-hundred-megabyte range, not the TensorFlow-sized
image; measure the built image with `docker image ls` and runtime memory in
Render before choosing an instance. Do not treat local estimates as a memory
guarantee.

The model is trained offline on simulated learners. To refresh the serving
artifact after training, back up `outputs/models/` first, run `make train`, then
run `make export-model` and rerun the parity test. Do not train inside the web
container or during startup.
