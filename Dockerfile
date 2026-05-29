FROM python:3.12-slim AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PYTHONPATH=/app \
    NEWSROOM_APP_USER=appuser

WORKDIR /app

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
COPY newsroom /app/newsroom
COPY gen_session.py /app/gen_session.py
COPY publisher /app/publisher
COPY scheduler /app/scheduler
COPY utils /app/utils
COPY worker /app/worker
COPY workers /app/workers
COPY docker /app/docker
COPY tools /app/tools

RUN apt-get update \
    && apt-get install -y --no-install-recommends gosu ffmpeg \
    && rm -rf /var/lib/apt/lists/* \
    && useradd --create-home --uid 1000 --shell /usr/sbin/nologin appuser \
    && mkdir -p /app/var/runtime \
    && chown -R appuser:appuser /app/var /app/tools /app/alembic

COPY docker/entrypoint.sh /entrypoint.sh
RUN chmod 755 /entrypoint.sh

USER root

HEALTHCHECK --interval=60s --timeout=20s --start-period=120s --retries=3 \
  CMD ["python", "/app/docker/healthcheck.py"]

ENTRYPOINT ["/entrypoint.sh"]
