FROM python:3.14-slim AS wheels

WORKDIR /build
COPY requirements-runtime.txt .
RUN python -m pip wheel --wheel-dir=/wheels -r requirements-runtime.txt

FROM python:3.14-slim AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    APP_ENV=production \
    MODEL_DIR=/app/outputs/models

WORKDIR /app
COPY --from=wheels /wheels /wheels
COPY requirements-runtime.txt .
RUN python -m pip install --no-index --find-links=/wheels -r requirements-runtime.txt \
    && rm -rf /wheels \
    && groupadd --system app \
    && useradd --system --gid app --home-dir /app app \
    && mkdir -p /app/outputs/models \
    && chown -R app:app /app

COPY --chown=app:app app ./app
COPY --chown=app:app src ./src
COPY --chown=app:app migrations ./migrations
COPY --chown=app:app static ./static
COPY --chown=app:app content ./content
COPY --chown=app:app alembic.ini ./
COPY --chown=app:app outputs/models/ ./outputs/models/

USER app
EXPOSE 10000

HEALTHCHECK --interval=30s --timeout=5s --start-period=30s --retries=3 \
  CMD python -c "import os; from urllib.request import urlopen; urlopen('http://127.0.0.1:' + os.getenv('PORT', '10000') + '/health', timeout=3)"

CMD ["sh", "-c", "alembic upgrade head && exec uvicorn app.main:app --host 0.0.0.0 --port \"${PORT:-10000}\" --proxy-headers --forwarded-allow-ips='*'"]
