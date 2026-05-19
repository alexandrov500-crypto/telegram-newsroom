#!/usr/bin/env bash
# Idempotent shadow mode — all publishes shadow-only.
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"
ENV_FILE="${ENV_FILE:-.env.production}"
REASON="${1:-emergency_shadow}"
AUDIT_LOG="${AUDIT_LOG:-var/log/emergency_audit.log}"
mkdir -p "$(dirname "$AUDIT_LOG")"
echo "$(date -u +%Y-%m-%dT%H:%M:%SZ) SHADOW reason=$REASON" >>"$AUDIT_LOG"

patch_env() {
  local k="$1" v="$2"
  if grep -q "^${k}=" "$ENV_FILE" 2>/dev/null; then
    sed -i.bak "s/^${k}=.*/${k}=${v}/" "$ENV_FILE"
  else
    echo "${k}=${v}" >>"$ENV_FILE"
  fi
}

if [[ -f "$ENV_FILE" ]]; then
  patch_env SHADOW_PUBLISH_ONLY true
  patch_env PRODUCTION_ROLLOUT_STAGE INTERNAL_SHADOW
  patch_env RELIABILITY_PUBLISH_MODE SHADOW
  patch_env AUTO_APPROVAL_ENABLED false
  rm -f "${ENV_FILE}.bak"
fi

COMPOSE_FILE="${COMPOSE_FILE:-deploy/production/docker-compose.production.yml}"
docker compose -f "$COMPOSE_FILE" --env-file "$ENV_FILE" up -d --force-recreate operator 2>/dev/null || true

echo "SHADOW MODE active. Verify: /startup_check · curl /safety"
echo "Audit: $AUDIT_LOG"
