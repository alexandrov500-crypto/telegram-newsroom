#!/usr/bin/env bash
# Continuous live health dashboard (terminal).
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"
ENV_FILE="${ENV_FILE:-.env.production}"
[[ -f "$ENV_FILE" ]] && set -a && source "$ENV_FILE" && set +a
BASE="${LIVE_WATCH_URL:-http://127.0.0.1:${HEALTH_HTTP_PORT:-8080}}"
INTERVAL="${LIVE_WATCH_INTERVAL:-15}"

red='\033[0;31m'; grn='\033[0;32m'; ylw='\033[0;33m'; nc='\033[0m'

while true; do
  clear
  echo -e "${grn}=== LIVE WATCH $(date -u +%H:%M:%S)Z ===${nc}"
  echo ""
  for label path in \
    "Health" "/health" \
    "Live status" "/live_status" \
    "Runtime identity" "/runtime_identity" \
    "Runtime loops" "/runtime_loops" \
    "Channel health" "/channel_health" \
    "Observation" "/observation_pulse"; do
    body="$(curl -sf "${BASE}${path}" 2>/dev/null | head -c 120 || echo FAIL)"
    if [[ "$body" == "FAIL" ]]; then
      echo -e "  ${red}✗${nc} $label"
    else
      echo -e "  ${grn}✓${nc} $label — $body"
    fi
  done
  echo ""
  metrics="$(curl -sf "${BASE}/metrics" 2>/dev/null | grep -E 'queue_|publish_|staging_shadow' | tail -5 || true)"
  if [[ -n "$metrics" ]]; then
    echo "$metrics"
  else
    echo -e "  ${ylw}(metrics warming up)${nc}"
  fi
  echo ""
  echo -e "${ylw}Escalation:${nc} emergency_shadow_mode.sh | emergency_rollback.sh | /war_room_start"
  sleep "$INTERVAL"
done
