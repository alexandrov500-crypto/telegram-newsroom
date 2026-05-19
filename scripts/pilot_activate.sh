#!/usr/bin/env bash
# Activate controlled public pilot — canary mode, real Telegram channels.
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

ENV_FILE="${ENV_FILE:-.env}"
if [[ ! -f "$ENV_FILE" && -f .env.production ]]; then
  ENV_FILE=.env.production
fi
COMPOSE_FILE="${COMPOSE_FILE:-deploy/production/docker-compose.production.yml}"
PILOT_TEMPLATE="deploy/production/env.pilot.example"

red() { printf '\033[0;31m%s\033[0m\n' "$*"; }
grn() { printf '\033[0;32m%s\033[0m\n' "$*"; }
ylw() { printf '\033[0;33m%s\033[0m\n' "$*"; }

echo "=========================================="
echo " CONTROLLED PUBLIC PILOT ACTIVATION"
echo "=========================================="

if [[ ! -f "$ENV_FILE" ]]; then
  if [[ -f "$PILOT_TEMPLATE" ]]; then
    ylw "Creating $ENV_FILE from $PILOT_TEMPLATE — FILL CHANNEL IDs before publishing."
    cp "$PILOT_TEMPLATE" "$ENV_FILE"
  else
    red "Missing $ENV_FILE"
    exit 1
  fi
fi

set -a
# shellcheck disable=SC1090
source "$ENV_FILE"
set +a

# Pilot defaults (do not override if already set in .env)
export CONTROLLED_LIVE_ENABLED="${CONTROLLED_LIVE_ENABLED:-true}"
export LIVE_MODE="${LIVE_MODE:-canary}"
export LIVE_CANARY_MAX_PER_HOUR="${LIVE_CANARY_MAX_PER_HOUR:-3}"
export LIVE_SUPERVISED_APPROVAL="${LIVE_SUPERVISED_APPROVAL:-true}"
export LIVE_FREEZE_ON_ANOMALY="${LIVE_FREEZE_ON_ANOMALY:-true}"
export LIVE_ENABLE_ROLLBACK="${LIVE_ENABLE_ROLLBACK:-true}"
export SHADOW_PUBLISH_ONLY="${SHADOW_PUBLISH_ONLY:-false}"
export STAGING_MODE="${STAGING_MODE:-false}"
export AUTO_APPROVAL_ENABLED="${AUTO_APPROVAL_ENABLED:-false}"

# Sync channel IDs
if [[ -n "${LIVE_PUBLIC_CHANNEL_ID:-}" ]]; then
  export TELEGRAM_CHANNEL_ID="${TELEGRAM_CHANNEL_ID:-$LIVE_PUBLIC_CHANNEL_ID}"
fi
if [[ -n "${LIVE_OPS_CHANNEL_ID:-}" ]]; then
  export TELEGRAM_OPERATOR_CHAT_ID="${TELEGRAM_OPERATOR_CHAT_ID:-$LIVE_OPS_CHANNEL_ID}"
fi
if [[ -n "${LIVE_SHADOW_CHANNEL_ID:-}" ]]; then
  export TELEGRAM_DIGEST_CHANNEL_ID="${TELEGRAM_DIGEST_CHANNEL_ID:-$LIVE_SHADOW_CHANNEL_ID}"
fi

echo ""
echo "=== Pilot configuration ==="
echo "  LIVE_MODE=$LIVE_MODE"
echo "  LIVE_CANARY_MAX_PER_HOUR=$LIVE_CANARY_MAX_PER_HOUR"
echo "  PUBLIC=$LIVE_PUBLIC_CHANNEL_ID"
echo "  OPS=$LIVE_OPS_CHANNEL_ID"
echo "  SHADOW=${LIVE_SHADOW_CHANNEL_ID:-optional}"

if [[ -z "${LIVE_PUBLIC_CHANNEL_ID:-}" ]] || [[ -z "${LIVE_OPS_CHANNEL_ID:-}" ]]; then
  red "Set LIVE_PUBLIC_CHANNEL_ID and LIVE_OPS_CHANNEL_ID in $ENV_FILE"
  exit 1
fi

if [[ "${LIVE_MODE}" != "canary" ]]; then
  ylw "WARN: pilot expects LIVE_MODE=canary (current: $LIVE_MODE)"
fi

echo ""
echo "=== Preflight (strict) ==="
PREFLIGHT_ARGS=(--env-file "$ENV_FILE" --strict)
if [[ "${SEND_PILOT_TEST_MESSAGES:-}" == "1" ]] || [[ "${1:-}" == "--send-test-message" ]]; then
  PREFLIGHT_ARGS+=(--send-test-message)
fi
if ! python3 scripts/pilot_preflight.py "${PREFLIGHT_ARGS[@]}"; then
  echo ""
  red "PILOT ACTIVATION ABORTED"
  red "Fix preflight failures before starting operator node."
  exit 1
fi

HEALTH_PORT="${HEALTH_HTTP_PORT:-8080}"
BASE="http://127.0.0.1:${HEALTH_PORT}"
LOG_FILE="${PILOT_LOG_FILE:-var/log/pilot-operator.log}"
PID_FILE="${PILOT_PID_FILE:-var/run/pilot-operator.pid}"

if ! command -v docker >/dev/null 2>&1; then
  ylw "Docker not found — using local operator mode (SQLite, no Redis required)"
  echo ""
  echo "=== Local operator (no Docker) ==="
  mkdir -p var/log var/run data
  # Force pilot runtime — .env may still have Docker/staging compose values.
export APP_ENV=pilot
export RUNTIME_PROFILE=minimal_pilot
export STAGING_MODE=false
export STAGING_STRICT_STARTUP=false
export SHADOW_PUBLISH_ONLY=false
export OPS_BURNIN_ENABLED=false
export LIVE_OPS_ENABLED=false
  export CLUSTER_ENABLED=false
  export REDIS_ENABLED=false
  export EVENT_BUS_BACKEND=inmemory
  export DATABASE_URL="${PILOT_DATABASE_URL:-sqlite+aiosqlite:///$(pwd)/data/newsroom.db}"
  export NODE_ROLE="${NODE_ROLE:-operator}"
  python3 -c "from bot.storage.db import init_database, default_db_path; init_database(default_db_path())"
  echo ""
  echo "=== Runtime ownership check ==="
  if ! python3 scripts/runtime_process_check.py; then
    if [[ "${PILOT_FORCE_RESTART:-}" == "1" ]] || [[ "${1:-}" == "--force" ]]; then
      ylw "Duplicates detected — running kill_all_operator_processes.sh"
      bash scripts/kill_all_operator_processes.sh
    else
      red "Duplicate or conflicting operator runtime detected."
      red "Run: bash scripts/kill_all_operator_processes.sh"
      red "Or: PILOT_FORCE_RESTART=1 bash scripts/pilot_activate.sh --force"
      exit 1
    fi
  fi
  if [[ -f "$PID_FILE" ]]; then
    old_pid="$(cat "$PID_FILE" 2>/dev/null || echo 0)"
    if [[ -n "$old_pid" ]] && kill -0 "$old_pid" 2>/dev/null; then
      ylw "Operator already running (pid $old_pid) — skip start"
    else
      rm -f "$PID_FILE"
    fi
  fi
  if [[ ! -f "$PID_FILE" ]]; then
    nohup python3 -m bot.main >>"$LOG_FILE" 2>&1 &
    echo $! >"$PID_FILE"
    grn "Started operator pid=$(cat "$PID_FILE") log=$LOG_FILE"
    sleep 2
    curl -sf "${BASE}/runtime_identity" 2>/dev/null | head -c 300 || ylw "runtime_identity not ready yet"
    echo ""
  fi
else
  echo ""
  echo "=== Infrastructure ==="
  docker compose -f "$COMPOSE_FILE" --env-file "$ENV_FILE" up -d postgres redis
  sleep 5
  docker compose -f "$COMPOSE_FILE" --env-file "$ENV_FILE" run --rm migrate

  echo ""
  echo "=== Operator node ==="
  docker compose -f "$COMPOSE_FILE" --env-file "$ENV_FILE" up -d operator
fi

echo ""
echo "=== Wait for health ==="
for i in {1..30}; do
  if curl -sf "${BASE}/health" >/dev/null 2>&1; then
    break
  fi
  sleep 2
done

if curl -sf "${BASE}/health" >/dev/null 2>&1; then
  grn "  [PASS] /health"
  curl -sf "${BASE}/pilot_readiness" | head -c 400 || true
  echo ""
else
  ylw "  [WARN] health not ready yet — check logs"
fi

echo ""
grn "=========================================="
grn " PILOT ACTIVATED (canary)"
grn "=========================================="
echo ""
echo "First live checklist:"
echo "  1. /live_status — mode=canary, not frozen"
echo "  2. /freeze_publishing then /resume_live — safety commands"
echo "  3. Publish ONE post with operator approval"
echo "  4. /publish_trace <id> — verify trace written"
echo "  5. /mark_good_post or /mark_bad_post <id>"
echo ""
echo "Monitor:  bash scripts/live_watch.sh"
echo "Preflight: python3 scripts/pilot_preflight.py --env-file $ENV_FILE"
echo "Emergency: /freeze_publishing · scripts/emergency_shadow_mode.sh"
echo ""
echo "Policy: max 3 posts/hour · no autonomous_live · freeze first if unsure"
if ! command -v docker >/dev/null 2>&1; then
  echo ""
  echo "Local mode: tail -f $LOG_FILE"
  echo "Stop: kill \$(cat $PID_FILE)"
  echo "Install Docker Desktop for full production compose stack."
fi
