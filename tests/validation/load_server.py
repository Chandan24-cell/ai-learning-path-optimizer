"""Temporary Locust server with per-virtual-user rate-limit identities."""

from __future__ import annotations

import os
import sys
from pathlib import Path

import uvicorn

# Direct script execution puts this directory, not the repository root, on
# sys.path. Add the root so the temporary test server can import the app.
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from app.main import app

if os.environ.get("VALIDATION_LOAD_TEST") != "1":
    raise SystemExit("Set VALIDATION_LOAD_TEST=1 only for this local load-test server")


@app.middleware("http")
async def isolate_test_client_rate_limits(request, call_next):
    client_id = request.headers.get("X-Load-Test-ID")
    if client_id:
        request.scope["client"] = (client_id, 0)
    return await call_next(request)


uvicorn.run(
    app,
    host="127.0.0.1",
    port=int(os.environ.get("PORT", "8765")),
    log_level="warning",
)
