#!/usr/bin/env bash
# Full emergency rollback — shadow + worker scale-down + operator restart.
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"
REASON="${1:-emergency_rollback}"
AUDIT_LOG="${AUDIT_LOG:-var/log/emergency_audit.log}"
mkdir -p "$(dirname "$AUDIT_LOG")"
echo "$(date -u +%Y-%m-%dT%H:%M:%SZ) ROLLBACK reason=$REASON" >>"$AUDIT_LOG"

bash "$(dirname "$0")/emergency_shadow_mode.sh" "$REASON"
bash "$(dirname "$0")/production_rollback.sh" "$REASON"

ENV_FILE="${ENV_FILE:-.env.production}"
COMPOSE_FILE="${COMPOSE_FILE:-deploy/production/docker-compose.production.yml}"
docker compose -f "$COMPOSE_FILE" \
  -f deploy/live-ops/docker-compose.workers.yml \
  --env-file "$ENV_FILE" stop publish-worker cognition-worker 2>/dev/null || true

echo "ROLLBACK complete. Telegram: /war_room_stop · /activation_rollback · /rollout_rollback"
echo "Verify: bash deploy/production/health-check-production.sh"
