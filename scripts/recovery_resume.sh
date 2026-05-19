#!/usr/bin/env bash
# Controlled recovery after emergency — does NOT auto-enable public publish.
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"
ENV_FILE="${ENV_FILE:-.env.production}"
AUDIT_LOG="${AUDIT_LOG:-var/log/emergency_audit.log}"
mkdir -p "$(dirname "$AUDIT_LOG")"
echo "$(date -u +%Y-%m-%dT%H:%M:%SZ) RECOVERY_RESUME" >>"$AUDIT_LOG"

if [[ -f "$ENV_FILE" ]]; then
  patch() { grep -q "^$1=" "$ENV_FILE" && sed -i.bak "s/^$1=.*/$1=$2/" "$ENV_FILE" || echo "$1=$2" >>"$ENV_FILE"; }
  patch PRODUCTION_GOVERNANCE_FREEZE false
  patch AUTO_APPROVAL_ENABLED false
  patch SHADOW_PUBLISH_ONLY true
  patch PRODUCTION_ROLLOUT_STAGE INTERNAL_SHADOW
  rm -f "${ENV_FILE}.bak"
fi

COMPOSE_FILE="${COMPOSE_FILE:-deploy/production/docker-compose.production.yml}"
docker compose -f "$COMPOSE_FILE" \
  -f deploy/live-ops/docker-compose.workers.yml \
  --env-file "$ENV_FILE" up -d

sleep 10
bash deploy/production/health-check-production.sh || true

echo "Recovery started — still SHADOW. Run /production_ready before ramp."
echo "Telegram: /take_shift · /go_live_check"
