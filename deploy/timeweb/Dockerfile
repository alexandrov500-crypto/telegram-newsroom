# Production image for Timeweb VPS (production-lite, app.main).
# Build context: repository root (see docker-compose.yml).

FROM python:3.12-slim AS runtime

ARG GIT_SHA=unknown
ARG BUILD_TIMESTAMP=unknown
ARG BUILD_BRANCH=unknown
ARG BUILD_VERSION=unknown

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PYTHONPATH=/app \
    TINI_SUBREAPER=1 \
    NEWSROOM_GIT_SHA=${GIT_SHA} \
    NEWSROOM_BUILD_TIMESTAMP=${BUILD_TIMESTAMP} \
    NEWSROOM_BUILD_BRANCH=${BUILD_BRANCH} \
    NEWSROOM_BUILD_VERSION=${BUILD_VERSION}

WORKDIR /app

RUN apt-get update \
    && apt-get install -y --no-install-recommends tini \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r /app/requirements.txt

COPY alembic.ini /app/alembic.ini
COPY alembic /app/alembic
COPY app /app/app
COPY ai /app/ai
COPY bot /app/bot
COPY collector /app/collector
COPY dashboard /app/dashboard
COPY db /app/db
COPY editorial /app/editorial
COPY observability /app/observability
COPY ops /app/ops
COPY publisher /app/publisher
COPY scheduler /app/scheduler
COPY utils /app/utils
COPY worker /app/worker
COPY workers /app/workers
COPY docker /app/docker
COPY tools /app/tools

RUN mkdir -p /data /data/runtime /data/backups /data/logs /data/sessions /app/var/runtime \
    && useradd --create-home --uid 1000 --shell /usr/sbin/nologin appuser \
    && chown -R appuser:appuser /data /app/var /app/tools /app/alembic

USER appuser

EXPOSE 8080

STOPSIGNAL SIGTERM

HEALTHCHECK --interval=60s --timeout=20s --start-period=120s --retries=3 \
  CMD ["python", "/app/docker/healthcheck.py"]

ENTRYPOINT ["/usr/bin/tini", "-s", "--"]
CMD ["python", "-m", "app.main"]
