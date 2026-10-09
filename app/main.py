"""FastAPI application entry point for the learning-path web app."""

from __future__ import annotations

import json
import logging
import time
from contextlib import asynccontextmanager
from pathlib import Path
from typing import cast
from uuid import uuid4

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from starlette.responses import Response

from app.config import settings
from app.database import SessionLocal
from app.routes.auth import account_router, limiter
from app.routes.auth import router as auth_router
from app.routes.discovery import manual_router
from app.routes.discovery import router as discovery_router
from app.routes.learning import router as learning_router
from app.routes.profile import router as profile_router
from app.routes.subjects import router as subjects_router
from app.routes.subjects import teacher_router
from app.services.recommender import get_mode

PROJECT_ROOT = Path(__file__).resolve().parent.parent
STATIC_DIR = PROJECT_ROOT / "static"
logger = logging.getLogger("app.requests")


@asynccontextmanager
async def lifespan(_app: FastAPI):
    mode = get_mode()
    logger.info("Saved recommender assets loaded: %s", mode)
    yield


production = settings.app_env == "production"
app = FastAPI(
    title="Personalized Learning Path Optimizer",
    docs_url=None if production else "/docs",
    redoc_url=None if production else "/redoc",
    openapi_url=None if production else "/openapi.json",
    lifespan=lifespan,
)
app.state.limiter = limiter


def rate_limit_exception_handler(request: Request, exc: Exception) -> Response:
    return _rate_limit_exceeded_handler(request, cast(RateLimitExceeded, exc))


app.add_exception_handler(RateLimitExceeded, rate_limit_exception_handler)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.allowed_origins,
    allow_credentials=False,
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE"],
    allow_headers=["Authorization", "Content-Type"],
)
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")
app.include_router(auth_router)
app.include_router(account_router)
app.include_router(learning_router)
app.include_router(profile_router)
app.include_router(subjects_router)
app.include_router(teacher_router)
app.include_router(discovery_router)
app.include_router(manual_router)


@app.middleware("http")
async def add_security_headers(request, call_next):
    request_id = uuid4().hex
    request.state.request_id = request_id
    started = time.perf_counter()
    status_code = 500
    try:
        response = await call_next(request)
        status_code = response.status_code
    except Exception:
        _log_request(request, request_id, status_code, time.perf_counter() - started)
        raise
    response.headers["X-Request-ID"] = request_id
    response.headers["Content-Security-Policy"] = (
        "default-src 'self'; script-src 'self'; style-src 'self'; "
        "img-src 'self' data:; connect-src 'self'; object-src 'none'; "
        "base-uri 'self'; frame-ancestors 'none'; form-action 'self'"
    )
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    if production:
        response.headers["Strict-Transport-Security"] = "max-age=63072000; includeSubDomains"
    _log_request(request, request_id, status_code, time.perf_counter() - started)
    return response


def _log_request(request: Request, request_id: str, status_code: int, duration: float) -> None:
    """Write request metadata only; request bodies and credentials are never logged."""
    logger.info(
        json.dumps(
            {
                "request_id": request_id,
                "method": request.method,
                "path": request.url.path,
                "status": status_code,
                "duration_ms": round(duration * 1000, 2),
            },
            separators=(",", ":"),
        )
    )


@app.get("/", include_in_schema=False)
def index():
    return FileResponse(STATIC_DIR / "index.html")


@app.get("/health", tags=["health"])
def health():
    return {"status": "ok"}


@app.get("/ready", tags=["health"])
def ready():
    """Report database connectivity and active recommender mode."""
    try:
        with SessionLocal() as db:
            db.execute(text("SELECT 1"))
        mode = get_mode()
    except (SQLAlchemyError, OSError, RuntimeError) as exc:
        logger.warning("Readiness check failed: %s", type(exc).__name__)
        raise HTTPException(status_code=503, detail="Application is not ready") from exc
    return {"status": "ready", "database": "ok", "recommender_mode": mode}
