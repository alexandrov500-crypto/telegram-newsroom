#!/usr/bin/env bash
# Production Telegram go-live activation — deterministic startup sequence.
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

ENV_FILE="${ENV_FILE:-.env.production}"
COMPOSE_FILE="${COMPOSE_FILE:-deploy/production/docker-compose.production.yml}"

if [[ ! -f "$ENV_FILE" ]]; then
  cp deploy/production/env.production.example "$ENV_FILE"
  echo "Created $ENV_FILE — fill Telegram secrets and channel IDs before continuing."
  exit 1
fi

set -a
# shellcheck disable=SC1090
source "$ENV_FILE"
set +a

export APP_ENV="${APP_ENV:-production}"
export STAGING_MODE="${STAGING_MODE:-false}"
export SHADOW_PUBLISH_ONLY="${SHADOW_PUBLISH_ONLY:-true}"
export PRODUCTION_STRICT_STARTUP="${PRODUCTION_STRICT_STARTUP:-true}"
export GO_LIVE_STRICT_STARTUP="${GO_LIVE_STRICT_STARTUP:-true}"
export PRODUCTION_ROLLOUT_STAGE="${PRODUCTION_ROLLOUT_STAGE:-INTERNAL_SHADOW}"
export RELIABILITY_PUBLISH_MODE="${RELIABILITY_PUBLISH_MODE:-SHADOW}"
export AUTO_APPROVAL_ENABLED="${AUTO_APPROVAL_ENABLED:-false}"

echo "=== Production activation ==="
echo "  APP_ENV=$APP_ENV"
echo "  PRODUCTION_ROLLOUT_STAGE=$PRODUCTION_ROLLOUT_STAGE"
echo "  SHADOW_PUBLISH_ONLY=$SHADOW_PUBLISH_ONLY"

echo ""
echo "[1/6] Pull images and start infra (Postgres, Redis)..."
docker compose -f "$COMPOSE_FILE" --env-file "$ENV_FILE" up -d postgres redis

echo "[2/6] Wait for Postgres and Redis health..."
for i in {1..30}; do
  if docker compose -f "$COMPOSE_FILE" --env-file "$ENV_FILE" ps postgres 2>/dev/null | grep -q healthy \
    && docker compose -f "$COMPOSE_FILE" --env-file "$ENV_FILE" ps redis 2>/dev/null | grep -q healthy; then
    break
  fi
  sleep 2
done

echo "[3/6] Run database init / migrations (operator one-shot)..."
docker compose -f "$COMPOSE_FILE" --env-file "$ENV_FILE" run --rm migrate

echo "[4/6] Start worker mesh overlay..."
docker compose -f "$COMPOSE_FILE" \
  -f deploy/live-ops/docker-compose.workers.yml \
  --env-file "$ENV_FILE" up -d

echo "[5/6] Start operator node (publisher + command surface)..."
docker compose -f "$COMPOSE_FILE" --env-file "$ENV_FILE" up -d operator

echo "[6/6] Health verification..."
sleep 12
bash deploy/production/health-check-production.sh

echo ""
echo "=== Activation complete ==="
echo "Telegram: /startup_check · /production_ready · /channel_status"
echo "Health:   curl -s http://127.0.0.1:\${HEALTH_HTTP_PORT:-8080}/go_live | jq ."
echo "Rollout:  /first_publication_status · /advance_publication"
