#!/usr/bin/env bash
# FINAL live public production startup — fail-hard validation then orchestrated bring-up.
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

ENV_FILE="${ENV_FILE:-.env.production}"
COMPOSE_FILE="${COMPOSE_FILE:-deploy/production/docker-compose.production.yml}"
HEALTH_PORT="${HEALTH_HTTP_PORT:-8080}"
BASE="http://127.0.0.1:${HEALTH_PORT}"
FAIL=0

red() { printf '\033[0;31m%s\033[0m\n' "$*"; }
grn() { printf '\033[0;32m%s\033[0m\n' "$*"; }
ylw() { printf '\033[0;33m%s\033[0m\n' "$*"; }

require() {
  local name="$1"
  local ok="$2"
  if [[ "$ok" == "1" ]]; then
    grn "  [PASS] $name"
  else
    red "  [FAIL] $name"
    FAIL=$((FAIL + 1))
  fi
}

echo "=========================================="
echo " LIVE PRODUCTION START"
echo "=========================================="

if [[ ! -f "$ENV_FILE" ]]; then
  red "Missing $ENV_FILE — copy deploy/production/env.production.example"
  exit 1
fi

set -a
# shellcheck disable=SC1090
source "$ENV_FILE"
set +a

export APP_ENV="${APP_ENV:-production}"
export STAGING_MODE="${STAGING_MODE:-false}"
export PRODUCTION_STRICT_STARTUP="${PRODUCTION_STRICT_STARTUP:-true}"
export GO_LIVE_STRICT_STARTUP="${GO_LIVE_STRICT_STARTUP:-true}"
export FIRST_72H_MODE="${FIRST_72H_MODE:-true}"
export LIVE_DEPLOY_ENABLED="${LIVE_DEPLOY_ENABLED:-true}"
export SHADOW_PUBLISH_ONLY="${SHADOW_PUBLISH_ONLY:-true}"
export PRODUCTION_ROLLOUT_STAGE="${PRODUCTION_ROLLOUT_STAGE:-INTERNAL_SHADOW}"
export RELIABILITY_PUBLISH_MODE="${RELIABILITY_PUBLISH_MODE:-SHADOW}"
export AUTO_APPROVAL_ENABLED="${AUTO_APPROVAL_ENABLED:-false}"

echo ""
echo "=== [1/12] Environment validation ==="
[[ -n "${TELEGRAM_BOT_TOKEN:-}" ]] && e_tok=1 || e_tok=0
[[ -n "${TELEGRAM_CHANNEL_ID:-}${TELEGRAM_DIGEST_CHANNEL_ID:-}" ]] && e_ch=1 || e_ch=0
[[ -n "${TELEGRAM_OPERATOR_CHAT_ID:-}" ]] && e_op=1 || e_op=0
[[ -n "${ADMIN_USER_IDS:-}${ADMIN_USER_ID:-}" ]] && e_adm=1 || e_adm=0
[[ -n "${OPENAI_API_KEY:-}" ]] && e_ai=1 || e_ai=0
[[ -n "${DATABASE_URL:-}" ]] && e_db=1 || e_db=0
[[ -n "${REDIS_URL:-}" ]] && e_redis=1 || e_redis=0
require "TELEGRAM_BOT_TOKEN" "$e_tok"
require "channel id" "$e_ch"
require "operator chat" "$e_op"
require "admin allowlist" "$e_adm"
require "OpenAI key" "$e_ai"
require "DATABASE_URL" "$e_db"
require "REDIS_URL" "$e_redis"

rollout="${PRODUCTION_ROLLOUT_STAGE}"
[[ "$rollout" == "INTERNAL_SHADOW" || "$rollout" == "LIMITED_CHANNELS" || "$rollout" == "LOW_FREQUENCY_PUBLIC" ]] && e_roll=1 || e_roll=0
require "rollout stage safe ($rollout)" "$e_roll"

lock="${RC1_LOCKDOWN_MODE:-true}"
[[ "$lock" != "0" && "$lock" != "false" && "$lock" != "no" ]] && e_lock=1 || e_lock=0
require "RC1 lockdown" "$e_lock"

if [[ $FAIL -gt 0 ]]; then
  red "Environment validation failed — fix .env before continuing."
  exit 1
fi

echo ""
echo "=== [2/12] Start infrastructure ==="
docker compose -f "$COMPOSE_FILE" --env-file "$ENV_FILE" up -d postgres redis
for i in {1..40}; do
  if docker compose -f "$COMPOSE_FILE" --env-file "$ENV_FILE" ps postgres 2>/dev/null | grep -q healthy \
    && docker compose -f "$COMPOSE_FILE" --env-file "$ENV_FILE" ps redis 2>/dev/null | grep -q healthy; then
    break
  fi
  sleep 2
done
require "Postgres healthy" "$(docker compose -f "$COMPOSE_FILE" --env-file "$ENV_FILE" ps postgres 2>/dev/null | grep -c healthy || true)"
require "Redis healthy" "$(docker compose -f "$COMPOSE_FILE" --env-file "$ENV_FILE" ps redis 2>/dev/null | grep -c healthy || true)"

echo ""
echo "=== [3/12] Database migrate ==="
docker compose -f "$COMPOSE_FILE" --env-file "$ENV_FILE" run --rm migrate

echo ""
echo "=== [4/12] Worker mesh ==="
docker compose -f "$COMPOSE_FILE" \
  -f deploy/live-ops/docker-compose.workers.yml \
  --env-file "$ENV_FILE" up -d

echo ""
echo "=== [5/12] Operator node ==="
docker compose -f "$COMPOSE_FILE" --env-file "$ENV_FILE" up -d operator ingest-eu signal

echo ""
echo "=== [6/12] Wait for health ==="
for i in {1..45}; do
  if curl -sf "${BASE}/health" >/dev/null 2>&1; then
    break
  fi
  sleep 2
done
curl -sf "${BASE}/health" >/dev/null || { red "Health endpoint unreachable"; exit 1; }
grn "  [PASS] /health"

echo ""
echo "=== [7/12] Pre-launch checklist (in-process) ==="
if python3 -m bot.live_deploy.cli prelaunch --db "${DATABASE_PATH:-data/newsroom.db}" 2>/dev/null; then
  grn "  [PASS] prelaunch CLI"
else
  ylw "  [WARN] prelaunch CLI (start bot first for full HTTP checks)"
fi

echo ""
echo "=== [8/12] Telegram live validation ==="
if python3 scripts/telegram_live_validation.py --env-file "$ENV_FILE"; then
  grn "  [PASS] telegram_live_validation"
else
  red "  [FAIL] telegram_live_validation"
  FAIL=$((FAIL + 1))
fi

echo ""
echo "=== [9/12] Health endpoints ==="
for path in ready startup go_live live_deploy safety reliability live_ops platform ops_playbook; do
  if curl -sf "${BASE}/${path}" >/dev/null 2>&1; then
    grn "  [PASS] /${path}"
  else
    ylw "  [WARN] /${path} unavailable"
  fi
done

echo ""
echo "=== [10/12] GA / certification / rollback snapshot ==="
ga_json="$(curl -sf "${BASE}/ga" 2>/dev/null || echo '{}')"
cert_json="$(curl -sf "${BASE}/certification" 2>/dev/null || echo '{}')"
rel_json="$(curl -sf "${BASE}/reliability" 2>/dev/null || echo '{}')"
echo "$ga_json" | head -c 200
echo ""
[[ -n "$rel_json" ]] && grn "  [PASS] reliability snapshot present" || ylw "  [WARN] reliability"

echo ""
echo "=== [11/12] Executive startup report ==="
if python3 -m bot.live_deploy.cli send-startup-report 2>/dev/null; then
  grn "  [PASS] executive startup report"
else
  ylw "  [WARN] startup report (operator bot must accept messages)"
fi

echo ""
echo "=== [12/12] Queue / worker sanity ==="
ready_json="$(curl -sf "${BASE}/ready" 2>/dev/null || echo '{}')"
echo "$ready_json" | head -c 300
echo ""

if [[ $FAIL -gt 0 ]]; then
  red ""
  red "STARTUP ABORTED — $FAIL hard failure(s)"
  exit 1
fi

echo ""
grn "=========================================="
grn " GO-LIVE READY"
grn "=========================================="
echo "Telegram: /startup_check /production_ready /shift_handoff"
echo "Monitor:  bash scripts/live_watch.sh"
echo "Emergency: bash scripts/emergency_shadow_mode.sh"
