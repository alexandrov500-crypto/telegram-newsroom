#!/usr/bin/env bash
# Read-only burn-in snapshot + readiness (no runtime changes).
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
export DATABASE_URL="${DATABASE_URL:-sqlite+aiosqlite:///./data/newsroom.db}"
LOG="${NEWSROOM_LOG:-logs/local-run.log}"

SINCE_EXTRA=()
if [ -n "${BURNIN_SINCE_TICK_ID:-}" ]; then
  SINCE_EXTRA=(--since-id "$BURNIN_SINCE_TICK_ID")
  echo "Using post-deploy window: tick id >= ${BURNIN_SINCE_TICK_ID}"
fi

echo "==> Burn-in snapshot"
if [ "${#SINCE_EXTRA[@]}" -gt 0 ]; then
  python3 tools/burnin_validation.py snapshot --log "$LOG" --write-json var/runtime/burnin_snapshot.json "${SINCE_EXTRA[@]}"
else
  python3 tools/burnin_validation.py snapshot --log "$LOG" --write-json var/runtime/burnin_snapshot.json
fi

echo ""
echo "==> Burn-in readiness"
if [ "${#SINCE_EXTRA[@]}" -gt 0 ]; then
  python3 tools/burnin_validation.py check --log "$LOG" --min-ticks "${BURNIN_MIN_TICKS:-3}" "${SINCE_EXTRA[@]}"
else
  python3 tools/burnin_validation.py check --log "$LOG" --min-ticks "${BURNIN_MIN_TICKS:-3}"
fi
rc=$?
case $rc in
  0) echo "Readiness: PASS" ;;
  2) echo "Readiness: CONDITIONAL (exit 2)" ;;
  *) echo "Readiness: FAIL (exit $rc)" ;;
esac
exit "$rc"
