#!/usr/bin/env bash
# Full local runtime cleanup: processes, stale markers (dead PIDs only).
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
RUNTIME_DIR="${RUNTIME_STATE_DIR:-var/runtime}"

pid_alive() {
  local p="$1"
  [[ -n "$p" && "$p" =~ ^[0-9]+$ ]] || return 1
  kill -0 "$p" 2>/dev/null
}

echo "== Phase 1: stop local Python runtimes =="
bash "$ROOT/scripts/stop_local_newsroom.sh" 2>/dev/null || true
pkill -9 -f "python.*-m app.main" 2>/dev/null || true
pkill -9 -f "Python -m app.main" 2>/dev/null || true
sleep 1

echo "== Process scan =="
if pgrep -fl "app.main" 2>/dev/null; then
  echo "ERROR: app.main still running"
  pgrep -fl "app.main" || true
  exit 1
fi
echo "OK: no app.main"

if command -v docker >/dev/null 2>&1; then
  echo "== Docker telegram containers =="
  docker ps --format '{{.Names}} {{.Status}}' 2>/dev/null | grep -i telegram || echo "(none running)"
fi

echo "== Stale runtime markers (${RUNTIME_DIR}) =="
ACTIVE="${RUNTIME_DIR}/active_runtime.json"
LOCK="${RUNTIME_DIR}/newsroom.lock"

if [[ -f "$ACTIVE" ]]; then
  STALE_PID="$(python3 -c "
import json, os, sys
p = '${ACTIVE}'
try:
    d = json.load(open(p))
    print(int(d.get('pid') or 0))
except Exception:
    print(0)
" 2>/dev/null || echo 0)"
  if [[ "$STALE_PID" != "0" ]] && pid_alive "$STALE_PID"; then
    echo "WARN: active_runtime.json pid=${STALE_PID} is ALIVE — not removing (investigate)"
  else
    echo "Removing stale active_runtime.json (pid=${STALE_PID} not alive)"
    rm -f "$ACTIVE"
  fi
else
  echo "No active_runtime.json"
fi

if [[ -f "$LOCK" ]]; then
  LOCK_PID="$(python3 -c "
import json
try:
    d=json.load(open('${LOCK}'))
    print(int(d.get('pid',0)))
except Exception:
    print(0)
" 2>/dev/null || echo 0)"
  if [[ "$LOCK_PID" != "0" ]] && pid_alive "$LOCK_PID"; then
    echo "WARN: newsroom.lock held by live pid=${LOCK_PID}"
  else
    echo "Removing orphan newsroom.lock"
    rm -f "$LOCK"
  fi
else
  echo "No newsroom.lock"
fi

echo "== Audit =="
python3 "$ROOT/tools/runtime_consistency_audit.py"
echo "CLEANUP_DONE"
