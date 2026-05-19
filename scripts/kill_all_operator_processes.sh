#!/usr/bin/env bash
# Stop every newsroom operator runtime (local processes, pid files, docker, locks).
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

ENV_FILE="${ENV_FILE:-.env}"
if [[ -f "$ENV_FILE" ]]; then
  set -a
  # shellcheck disable=SC1090
  source "$ENV_FILE"
  set +a
fi

PID_FILE="${PILOT_PID_FILE:-var/run/pilot-operator.pid}"
LOCK_FILE="${RUNTIME_LOCK_FILE:-var/run/operator-runtime.lock}"
COMPOSE_FILE="${COMPOSE_FILE:-deploy/production/docker-compose.production.yml}"

red() { printf '\033[0;31m%s\033[0m\n' "$*"; }
grn() { printf '\033[0;32m%s\033[0m\n' "$*"; }
ylw() { printf '\033[0;33m%s\033[0m\n' "$*"; }

echo "=========================================="
echo " KILL ALL OPERATOR RUNTIMES"
echo "=========================================="

kill_pid() {
  local pid="$1"
  local label="$2"
  if [[ -z "$pid" ]] || [[ "$pid" -le 0 ]]; then
    return 0
  fi
  if kill -0 "$pid" 2>/dev/null; then
    ylw "Stopping $label pid=$pid"
    kill "$pid" 2>/dev/null || true
    sleep 1
    if kill -0 "$pid" 2>/dev/null; then
      ylw "Force kill $label pid=$pid"
      kill -9 "$pid" 2>/dev/null || true
    fi
  fi
}

if [[ -f "$PID_FILE" ]]; then
  kill_pid "$(cat "$PID_FILE" 2>/dev/null || echo 0)" "pid-file"
  rm -f "$PID_FILE"
  grn "Removed $PID_FILE"
fi

if command -v docker >/dev/null 2>&1 && [[ -f "$COMPOSE_FILE" ]]; then
  ylw "Stopping docker operator (if running)..."
  docker compose -f "$COMPOSE_FILE" --env-file "$ENV_FILE" stop operator 2>/dev/null || true
fi

ylw "Stopping bot.main python processes..."
pkill -f "python.*-m bot\.main" 2>/dev/null || true
pkill -f "python.*bot/main\.py" 2>/dev/null || true
sleep 1
pkill -9 -f "python.*-m bot\.main" 2>/dev/null || true

rm -f "$LOCK_FILE"
mkdir -p var/run
grn "Cleared lock file $LOCK_FILE"

echo ""
echo "=== Verification ==="
if python3 scripts/runtime_process_check.py; then
  grn "No duplicate operator processes remain."
else
  red "Some processes may still be running — inspect output above."
  exit 1
fi

echo ""
grn "Clean restart: bash scripts/pilot_activate.sh"
echo "Then: curl -s http://127.0.0.1:\${HEALTH_HTTP_PORT:-8080}/runtime_identity | python3 -m json.tool"
