#!/usr/bin/env bash
# Restore Gram VPN / Xray tunnel on Timeweb VPS after config loss or compose recreate.
set -euo pipefail

BASE="${NEWSROOM_BASE:-/opt/newsroom}"
COMPOSE="docker compose -f ${BASE}/deploy/timeweb/docker-compose.yml -f ${BASE}/deploy/timeweb/docker-compose.override.yml"
VPN_DIR="${BASE}/deploy/timeweb/vpn"
URL_FILE="${BASE}/deploy/timeweb/vpn_sub_url.txt"
XRAY_DATA="${BASE}/xray-data"

echo "=== fix xray-data layout ==="
if [[ -d "${XRAY_DATA}/config.json" && ! -f "${XRAY_DATA}/config.json" ]]; then
  docker run --rm -v "${XRAY_DATA}:/data" alpine sh -c "rm -rf /data/config.json"
fi
mkdir -p "${XRAY_DATA}"
chown -R newsroom:newsroom "${XRAY_DATA}" 2>/dev/null || true

if [[ ! -f "${URL_FILE}" && -z "${VPN_SUBSCRIPTION_URL:-}" ]]; then
  echo "ERROR: missing ${URL_FILE} and VPN_SUBSCRIPTION_URL is unset" >&2
  exit 1
fi

echo "=== build vpn-probe image ==="
docker build -t vpn-probe:local "${VPN_DIR}"

echo "=== ensure xray container is up ==="
${COMPOSE} up -d xray

echo "=== refresh xray config from subscription ==="
python3 "${VPN_DIR}/vpn_refresh.py"

echo "=== restart newsroom after proxy restore ==="
${COMPOSE} restart newsroom

for i in $(seq 1 24); do
  st=$(docker inspect --format='{{.State.Health.Status}}' telegram-newsroom 2>/dev/null || echo starting)
  echo "newsroom health=${st} (${i}/24)"
  [[ "${st}" == "healthy" ]] && break
  sleep 10
done

docker ps --filter name=xray --filter name=telegram-newsroom --format "{{.Names}} {{.Status}}"
curl -sf http://127.0.0.1:8080/health | python3 -c "import json,sys; d=json.load(sys.stdin); print('telegram', d.get('dependencies',{}).get('telegram_api',{}).get('status'), 'telethon', d.get('dependencies',{}).get('telethon',{}).get('status'))"
