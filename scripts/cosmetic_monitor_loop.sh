#!/usr/bin/env bash
# Periodic cosmetic audit on VPS: detect fallback media when source cache exists, auto-fix.
set -euo pipefail

REPO="$(cd "$(dirname "$0")/.." && pwd)"
VPS_HOST="${COSMETIC_VPS_HOST:-newsroom@213.171.3.133}"
VPS_CONTAINER="${COSMETIC_VPS_CONTAINER:-telegram-newsroom}"
INTERVAL_SEC="${COSMETIC_AUDIT_INTERVAL_SEC:-900}"

run_audit() {
  scp -q "$REPO/tools/cosmetic_publish_audit.py" "$REPO/tools/fix_published_media.py" "${VPS_HOST}:/tmp/" 2>/dev/null || true
  ssh "$VPS_HOST" "docker cp /tmp/cosmetic_publish_audit.py ${VPS_CONTAINER}:/app/tools/cosmetic_publish_audit.py && \
    docker cp /tmp/fix_published_media.py ${VPS_CONTAINER}:/app/tools/fix_published_media.py && \
    docker exec ${VPS_CONTAINER} python3 /app/tools/cosmetic_publish_audit.py --limit 30 --fix"
}

case "${1:-once}" in
  once)
    run_audit
    ;;
  loop)
    echo "cosmetic_monitor interval=${INTERVAL_SEC}s host=${VPS_HOST}"
    run_audit || true
    while true; do
      sleep "$INTERVAL_SEC"
      run_audit || true
      echo "AGENT_LOOP_TICK_cosmetic {\"prompt\":\"Run cosmetic publish audit on VPS and fix media fallback defects in recent drafts. Report fixable issues to user if any remain.\"}"
    done
    ;;
  *)
    echo "Usage: $0 [once|loop]" >&2
    exit 1
    ;;
esac
