# AI assistant instructions

Read [PROJECT_STATE.md](PROJECT_STATE.md) before changing this project. At the end of every task, update `PROJECT_STATE.md` with the current status and any changed decisions, risks, or run instructions.

Preserve `outputs/app.db`; use temporary databases for tests and validation. Back up `outputs/models/` before running `python run_all.py`, because the pipeline overwrites generated artifacts. Do not add a Git remote, push, create GitHub Actions, or deploy to the cloud. Keep changes local and scoped to the requested phase.
