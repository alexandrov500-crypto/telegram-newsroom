#!/usr/bin/env bash
# Build production .env for VPS from Mac local .env + required Telethon vars.
# Usage:
#   export TELEGRAM_API_ID=...
#   export TELEGRAM_API_HASH=...
#   export TELETHON_SESSION_STRING=...
#   export SOURCE_CHANNELS='@ch1,@ch2'
#   bash deploy/timeweb/scripts/build-vps-env.sh
# Output: deploy/timeweb/.env.vps (gitignored) — scp to server

set -euo pipefail

ROOT="$(cd "$(dirname "$0")/../../.." && pwd)"
OUT="${ROOT}/deploy/timeweb/.env.vps"
EXAMPLE="${ROOT}/deploy/timeweb/.env.example"
LOCAL="${ROOT}/.env"

die() { echo "ERROR: $*" >&2; exit 1; }

[[ -f "${EXAMPLE}" ]] || die "missing .env.example"

# shellcheck disable=SC1090
[[ -f "${LOCAL}" ]] && source "${LOCAL}"

: "${OPENAI_API_KEY:?set OPENAI_API_KEY in ${LOCAL}}"
: "${BOT_TOKEN:=${TELEGRAM_BOT_TOKEN:-}}"
: "${BOT_TOKEN:?set BOT_TOKEN}"
: "${TELEGRAM_API_ID:?export TELEGRAM_API_ID}"
: "${TELEGRAM_API_HASH:?export TELEGRAM_API_HASH}"
: "${TELETHON_SESSION_STRING:?export TELETHON_SESSION_STRING after tools/export_telethon_session.py}"
: "${SOURCE_CHANNELS:?export SOURCE_CHANNELS e.g. @channel1,@channel2}"

ADMIN_USER_ID="${ADMIN_USER_ID:-${ADMIN_USER_IDS:-167395657}}"
TARGET_CHANNEL_ID="${TARGET_CHANNEL_ID:-${LIVE_PUBLIC_CHANNEL_ID:-${TELEGRAM_CHANNEL_ID:--1003934479919}}}"

cp "${EXAMPLE}" "${OUT}"

set_kv() {
  local k="$1" v="$2"
  if grep -q "^${k}=" "${OUT}"; then
    sed -i.bak "s|^${k}=.*|${k}=${v}|" "${OUT}"
  else
    echo "${k}=${v}" >> "${OUT}"
  fi
}

# VPS uses Yandex via y2o relay (OPENAI_BASE_URL + sk-y2o-*). Do not overwrite with Mac sk-proj.
if [[ -f "${ROOT}/deploy/timeweb/.env.bak" ]] && [[ "${OPENAI_API_KEY:-}" == sk-proj-* ]]; then
  echo "WARN: local OPENAI_API_KEY looks like OpenAI direct; keep deploy/timeweb/.env.bak y2o keys for VPS" >&2
  prev="${ROOT}/deploy/timeweb/.env"
  if [[ -f "${prev}" ]]; then
    # shellcheck disable=SC1090
    source "${prev}"
  fi
fi
set_kv OPENAI_API_KEY "${OPENAI_API_KEY}"
set_kv BOT_TOKEN "${BOT_TOKEN}"
set_kv TELEGRAM_API_ID "${TELEGRAM_API_ID}"
set_kv TELEGRAM_API_HASH "${TELEGRAM_API_HASH}"
set_kv TELETHON_SESSION_STRING "${TELETHON_SESSION_STRING}"
set_kv ADMIN_USER_ID "${ADMIN_USER_ID}"
set_kv TARGET_CHANNEL_ID "${TARGET_CHANNEL_ID}"
set_kv SOURCE_CHANNELS "${SOURCE_CHANNELS}"
set_kv APP_ENV production
set_kv APP_DEPLOYMENT_PROFILE production-lite
set_kv NEWSROOM_PROFILE production-lite
set_kv DRY_RUN false
set_kv ENV production
set_kv RUNTIME_OPERATIONAL_MODE "${RUNTIME_OPERATIONAL_MODE:-production}"
set_kv PIPELINE_BOOTSTRAP_ON_START "${PIPELINE_BOOTSTRAP_ON_START:-true}"
set_kv PIPELINE_INTERVAL_MINUTES "${PIPELINE_INTERVAL_MINUTES:-15}"
set_kv TELEGRAM_POLLING_ENABLED "${TELEGRAM_POLLING_ENABLED:-true}"
set_kv LOG_LEVEL "${LOG_LEVEL:-INFO}"
set_kv DATABASE_URL "sqlite+aiosqlite:////data/newsroom.db"
set_kv RUNTIME_STATE_DIR "/data/runtime"
set_kv HEALTHCHECK_TIMEOUT_SEC "${HEALTHCHECK_TIMEOUT_SEC:-20}"
set_kv TELEGRAM_STARTUP_HEALTH_MAX_RETRIES "${TELEGRAM_STARTUP_HEALTH_MAX_RETRIES:-1}"
set_kv TELETHON_SESSION_PATH "/data/sessions/telethon.session"
set_kv TELETHON_PROXY "${TELETHON_PROXY:-socks5://xray:1080}"
set_kv TELEGRAM_BOT_PROXY "${TELEGRAM_BOT_PROXY:-http://xray:1081}"
set_kv OPENAI_BASE_URL "${OPENAI_BASE_URL:-http://y2o:8520/v1}"
set_kv YANDEX_API_KEY "${YANDEX_API_KEY:-}"
set_kv YANDEX_FOLDER_ID "${YANDEX_FOLDER_ID:-}"
set_kv GROWTH_CADENCE_ENABLED "${GROWTH_CADENCE_ENABLED:-false}"
set_kv NEWSROOM_CB_BRIEF_FORMAT "${NEWSROOM_CB_BRIEF_FORMAT:-true}"
set_kv SUMMARY_STYLE "${SUMMARY_STYLE:-cb-economics-brief}"
set_kv HEADLINE_MODE "${HEADLINE_MODE:-json}"
set_kv EDITORIAL_TUNING_PATH "${EDITORIAL_TUNING_PATH:-/app/config/editorial_tuning.yaml}"

rm -f "${OUT}.bak"
chmod 600 "${OUT}"

cp "${OUT}" "${ROOT}/deploy/timeweb/.env"
chmod 600 "${ROOT}/deploy/timeweb/.env"

echo "Wrote ${OUT} and deploy/timeweb/.env (local compose + VPS template)"
echo "Copy to VPS:"
echo "  scp ${OUT} newsroom@YOUR_VPS:/opt/newsroom/deploy/timeweb/.env"
