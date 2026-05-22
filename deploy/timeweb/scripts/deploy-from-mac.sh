#!/usr/bin/env bash
# Run on Mac after: ssh-copy-id -i ~/.ssh/id_ed25519.pub newsroom@213.171.3.133
set -euo pipefail

VPS_HOST="${VPS_HOST:-213.171.3.133}"
VPS_USER="${VPS_USER:-newsroom}"
REPO_LOCAL="$(cd "$(dirname "$0")/../../.." && pwd)"
LOCAL_ENV="${REPO_LOCAL}/.env"
SSH_OPTS=(-o BatchMode=yes -o ConnectTimeout=20)

echo "[mac] testing SSH to ${VPS_USER}@${VPS_HOST}..."
ssh "${SSH_OPTS[@]}" "${VPS_USER}@${VPS_HOST}" 'echo SSH OK; hostname'

# shellcheck source=/dev/null
if [[ -f "${LOCAL_ENV}" ]]; then
  set -a
  # shellcheck disable=SC1090
  source "${LOCAL_ENV}"
  set +a
fi

: "${OPENAI_API_KEY:?set OPENAI_API_KEY in ${LOCAL_ENV}}"
: "${BOT_TOKEN:=${TELEGRAM_BOT_TOKEN:-}}"
: "${BOT_TOKEN:?set BOT_TOKEN in ${LOCAL_ENV}}"
: "${TELEGRAM_API_ID:?set TELEGRAM_API_ID in ${LOCAL_ENV} or export before run}"
: "${TELEGRAM_API_HASH:?set TELEGRAM_API_HASH in ${LOCAL_ENV} or export before run}"

ADMIN_USER_ID="${ADMIN_USER_ID:-${ADMIN_USER_IDS:-${TELEGRAM_OPERATOR_CHAT_ID:-}}}"
TARGET_CHANNEL_ID="${TARGET_CHANNEL_ID:-${LIVE_PUBLIC_CHANNEL_ID:-${TELEGRAM_CHANNEL_ID:-}}}"
SOURCE_CHANNELS="${SOURCE_CHANNELS:-@${LIVE_ALLOWED_SOURCES:-channel1}}"

ENV_VPS="${REPO_LOCAL}/deploy/timeweb/.env"
if [[ ! -f "${ENV_VPS}" ]]; then
  bash "${REPO_LOCAL}/deploy/timeweb/scripts/build-vps-env.sh"
fi

echo "[mac] syncing .env to VPS..."
scp "${SSH_OPTS[@]}" "${ENV_VPS}" "${VPS_USER}@${VPS_HOST}:/opt/newsroom/deploy/timeweb/.env"
ssh "${SSH_OPTS[@]}" "${VPS_USER}@${VPS_HOST}" "chmod 600 /opt/newsroom/deploy/timeweb/.env"

echo "[mac] syncing deploy script and running remote production-deploy..."
ssh "${SSH_OPTS[@]}" "${VPS_USER}@${VPS_HOST}" "mkdir -p /opt/newsroom/deploy/timeweb/scripts"

rsync -avz --relative \
  "${REPO_LOCAL}/deploy/timeweb/scripts/production-deploy.sh" \
  "${REPO_LOCAL}/deploy/timeweb/docker-compose.yml" \
  "${REPO_LOCAL}/deploy/timeweb/Dockerfile" \
  "${REPO_LOCAL}/deploy/timeweb/.env.example" \
  "${VPS_USER}@${VPS_HOST}:/opt/newsroom/"

ssh "${SSH_OPTS[@]}" "${VPS_USER}@${VPS_HOST}" bash -s <<REMOTE
set -euo pipefail
export OPENAI_API_KEY='${OPENAI_API_KEY}'
export TELEGRAM_API_ID='${TELEGRAM_API_ID}'
export TELEGRAM_API_HASH='${TELEGRAM_API_HASH}'
export BOT_TOKEN='${BOT_TOKEN}'
export ADMIN_USER_ID='${ADMIN_USER_ID}'
export TARGET_CHANNEL_ID='${TARGET_CHANNEL_ID}'
export SOURCE_CHANNELS='${SOURCE_CHANNELS}'
export TELETHON_SESSION_STRING='${TELETHON_SESSION_STRING:-}'
export BRANCH='${BRANCH:-main}'
cd /opt/newsroom
git fetch origin || true
git checkout "\$BRANCH" || true
bash deploy/timeweb/scripts/production-deploy.sh
REMOTE

echo "[mac] done."
