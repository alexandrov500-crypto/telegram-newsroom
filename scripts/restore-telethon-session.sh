#!/usr/bin/env bash
# After a fresh Telethon login on Mac, push session to VPS and restart newsroom.
#
#   python gen_session.py --write-env   # or --phone/--send-code/--code flow
#   python gen_session.py --verify
#   bash scripts/restore-telethon-session.sh --deploy-only
#
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "${ROOT}"

VPS_HOST="${VPS_HOST:-213.171.3.133}"
VPS_USER="${VPS_USER:-newsroom}"
SSH_OPTS=(-o BatchMode=yes -o ConnectTimeout=20)
DEPLOY_ONLY=false

usage() {
  echo "Usage: $0 [--deploy-only]" >&2
  echo "  Verifies local TELETHON_SESSION_STRING, rebuilds deploy/timeweb/.env, syncs to VPS, starts newsroom." >&2
  exit 1
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --deploy-only) DEPLOY_ONLY=true; shift ;;
    -h|--help) usage ;;
    *) echo "Unknown arg: $1" >&2; usage ;;
  esac
done

if [[ ! -f "${ROOT}/.env" ]]; then
  echo "ERROR: ${ROOT}/.env missing" >&2
  exit 1
fi

echo "[restore] verify local session..."
python3 gen_session.py --verify

echo "[restore] build deploy/timeweb/.env from local .env..."
bash deploy/timeweb/scripts/build-vps-env.sh

ENV_VPS="${ROOT}/deploy/timeweb/.env"
echo "[restore] scp .env → ${VPS_USER}@${VPS_HOST}:/opt/newsroom/deploy/timeweb/.env"
scp "${SSH_OPTS[@]}" "${ENV_VPS}" "${VPS_USER}@${VPS_HOST}:/opt/newsroom/deploy/timeweb/.env"
ssh "${SSH_OPTS[@]}" "${VPS_USER}@${VPS_HOST}" "chmod 600 /opt/newsroom/deploy/timeweb/.env"

if [[ "${DEPLOY_ONLY}" == true ]]; then
  echo "[restore] restart newsroom (no image rebuild)..."
  ssh "${SSH_OPTS[@]}" "${VPS_USER}@${VPS_HOST}" bash -s <<'REMOTE'
set -euo pipefail
cd /opt/newsroom/deploy/timeweb
docker compose up -d newsroom
for i in $(seq 1 24); do
  st=$(docker inspect --format='{{.State.Health.Status}}' telegram-newsroom 2>/dev/null || echo starting)
  echo "[restore] health ${i}/24: ${st}"
  [[ "${st}" == healthy ]] && break
  sleep 5
done
docker exec telegram-newsroom python gen_session.py --verify
REMOTE
else
  echo "[restore] full production-deploy on VPS..."
  bash deploy/timeweb/scripts/deploy-from-mac.sh
fi

echo "[restore] done."
