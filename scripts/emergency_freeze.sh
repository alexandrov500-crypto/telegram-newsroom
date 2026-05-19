#!/usr/bin/env bash
# Idempotent governance freeze — blocks publishes, notifies operators.
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"
ENV_FILE="${ENV_FILE:-.env.production}"
REASON="${1:-operator_emergency_freeze}"
AUDIT_LOG="${AUDIT_LOG:-var/log/emergency_audit.log}"
mkdir -p "$(dirname "$AUDIT_LOG")"
echo "$(date -u +%Y-%m-%dT%H:%M:%SZ) FREEZE reason=$REASON" >>"$AUDIT_LOG"

if [[ -f "$ENV_FILE" ]]; then
  for key in AUTO_APPROVAL_ENABLED PRODUCTION_GOVERNANCE_FREEZE; do
    if grep -q "^${key}=" "$ENV_FILE" 2>/dev/null; then
      sed -i.bak "s/^${key}=.*/${key}=true/" "$ENV_FILE" 2>/dev/null || true
    else
      echo "${key}=true" >>"$ENV_FILE"
    fi
  done
  rm -f "${ENV_FILE}.bak"
fi

export PRODUCTION_GOVERNANCE_FREEZE=true
export AUTO_APPROVAL_ENABLED=false

COMPOSE_FILE="${COMPOSE_FILE:-deploy/production/docker-compose.production.yml}"
docker compose -f "$COMPOSE_FILE" --env-file "$ENV_FILE" up -d --force-recreate operator 2>/dev/null || true

echo "FREEZE active. Telegram: /governance_status · /rollout_rollback"
echo "Audit: $AUDIT_LOG"
