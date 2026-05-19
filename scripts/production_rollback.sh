#!/usr/bin/env bash
# Emergency production rollback — shadow mode + stop workers.
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

ENV_FILE="${ENV_FILE:-.env.production}"
COMPOSE_FILE="${COMPOSE_FILE:-deploy/production/docker-compose.production.yml}"
REASON="${1:-operator_emergency_rollback}"

echo "=== PRODUCTION ROLLBACK ==="
echo "Reason: $REASON"

export SHADOW_PUBLISH_ONLY=true
export PRODUCTION_ROLLOUT_STAGE=INTERNAL_SHADOW
export RELIABILITY_PUBLISH_MODE=SHADOW
export AUTO_APPROVAL_ENABLED=false

if [[ -f "$ENV_FILE" ]]; then
  if grep -q '^SHADOW_PUBLISH_ONLY=' "$ENV_FILE"; then
    sed -i.bak 's/^SHADOW_PUBLISH_ONLY=.*/SHADOW_PUBLISH_ONLY=true/' "$ENV_FILE"
  else
    echo "SHADOW_PUBLISH_ONLY=true" >>"$ENV_FILE"
  fi
  if grep -q '^PRODUCTION_ROLLOUT_STAGE=' "$ENV_FILE"; then
    sed -i.bak 's/^PRODUCTION_ROLLOUT_STAGE=.*/PRODUCTION_ROLLOUT_STAGE=INTERNAL_SHADOW/' "$ENV_FILE"
  else
    echo "PRODUCTION_ROLLOUT_STAGE=INTERNAL_SHADOW" >>"$ENV_FILE"
  fi
  rm -f "${ENV_FILE}.bak"
fi

echo "[1] Scale down publish-heavy workers..."
docker compose -f "$COMPOSE_FILE" \
  -f deploy/live-ops/docker-compose.workers.yml \
  --env-file "$ENV_FILE" stop publish-worker cognition-worker 2>/dev/null || true

echo "[2] Restart operator with shadow env..."
docker compose -f "$COMPOSE_FILE" --env-file "$ENV_FILE" up -d --force-recreate operator

echo "[3] Verify health..."
sleep 8
curl -sf "http://127.0.0.1:${HEALTH_HTTP_PORT:-8080}/safety" | head -c 500 || true
echo ""
echo "Telegram: send /rollout_rollback and /activation_rollback to operator bot"
echo "Verify:   /startup_check · /safety_status"
