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

rm -f "${OUT}.bak"
chmod 600 "${OUT}"

echo "Wrote ${OUT}"
echo "Copy to VPS:"
echo "  scp ${OUT} newsroom@213.171.3.133:/opt/newsroom/deploy/timeweb/.env"
