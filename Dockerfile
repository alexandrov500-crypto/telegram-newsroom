FROM python:3.12-slim AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PYTHONPATH=/app

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
COPY publisher /app/publisher
COPY scheduler /app/scheduler
COPY utils /app/utils
COPY worker /app/worker
COPY workers /app/workers
COPY docker /app/docker
COPY tools /app/tools

RUN mkdir -p /app/var/runtime \
    && useradd --create-home --shell /usr/sbin/nologin appuser \
    && mkdir -p /data \
    && chown -R appuser:appuser /data /app/var /app/tools /app/alembic

USER appuser

HEALTHCHECK --interval=60s --timeout=15s --start-period=45s --retries=3 \
  CMD ["python", "/app/docker/healthcheck.py"]

CMD ["python", "-m", "app.main"]
