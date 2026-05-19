#!/usr/bin/env bash
# 48h operational observation loop — pulse every 45 minutes (configurable).
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

ENV_FILE="${ENV_FILE:-.env}"
[[ -f "$ENV_FILE" ]] && set -a && source "$ENV_FILE" && set +a

INTERVAL="${OPS_OBSERVE_INTERVAL_SEC:-2700}"
BASE="${OPS_HEALTH_BASE:-http://127.0.0.1:${HEALTH_HTTP_PORT:-8080}}"
LOG="${OPS_OBSERVE_LOG:-var/log/ops-observe-48h.log}"

mkdir -p var/log var/ops/pulses var/ops/daily

red() { printf '\033[0;31m%s\033[0m\n' "$*"; }
grn() { printf '\033[0;32m%s\033[0m\n' "$*"; }
ylw() { printf '\033[0;33m%s\033[0m\n' "$*"; }

echo "48h observation watch started interval=${INTERVAL}s base=${BASE}"
echo "Log: ${LOG}"
echo "Stop: Ctrl+C"
echo ""

while true; do
  ts="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
  echo "=== pulse ${ts} ===" | tee -a "$LOG"
  if python3 scripts/ops_observe_pulse.py --base-url "$BASE" 2>&1 | tee -a "$LOG"; then
    ec=0
  else
    ec=$?
  fi
  if [[ "$ec" -eq 2 ]]; then
    red "CRITICAL anomaly — consider /freeze_publishing"
  elif [[ "$ec" -eq 1 ]]; then
    ylw "Warning-level signals detected"
  else
    grn "Pulse OK"
  fi
  hour_utc="$(date -u +%H)"
  if [[ "$hour_utc" == "00" ]]; then
    ylw "Running daily snapshot..."
    python3 scripts/ops_daily_snapshot.py --base-url "$BASE" 2>&1 | tee -a "$LOG" || true
  fi
  sleep "$INTERVAL"
done
