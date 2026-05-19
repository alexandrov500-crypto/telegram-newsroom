#!/usr/bin/env bash
# Graceful production shutdown.
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

ENV_FILE="${ENV_FILE:-.env.production}"
COMPOSE_FILE="${COMPOSE_FILE:-deploy/production/docker-compose.production.yml}"

echo "=== Graceful shutdown ==="
docker compose -f "$COMPOSE_FILE" \
  -f deploy/live-ops/docker-compose.workers.yml \
  --env-file "$ENV_FILE" stop operator ingest-worker cognition-worker publish-worker recovery-worker 2>/dev/null || true

docker compose -f "$COMPOSE_FILE" --env-file "$ENV_FILE" stop signal digest ingest-eu ingest-us 2>/dev/null || true

echo "Workers stopped. Infra (postgres/redis) left running. Use:"
echo "  docker compose -f $COMPOSE_FILE --env-file $ENV_FILE down"
echo "to remove all containers."
