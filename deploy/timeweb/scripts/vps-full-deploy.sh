#!/usr/bin/env bash
# Run ON VPS after .env is in place: bash /opt/newsroom/deploy/timeweb/scripts/vps-full-deploy.sh
set -euo pipefail

COMPOSE="docker compose -f /opt/newsroom/deploy/timeweb/docker-compose.yml"
REPO=/opt/newsroom

cd "${REPO}"
git fetch origin
git checkout v3-live-telegram-validation
git pull origin v3-live-telegram-validation || git reset --hard origin/v3-live-telegram-validation

mkdir -p "${REPO}/data/runtime" "${REPO}/data/backups" "${REPO}/logs" "${REPO}/sessions"
chown -R 1000:1000 "${REPO}/data" "${REPO}/logs" "${REPO}/sessions" 2>/dev/null || true
chmod 700 "${REPO}/sessions" 2>/dev/null || true

[[ -f /opt/newsroom/deploy/timeweb/.env ]] || { echo "Missing .env — copy from Mac first"; exit 1; }
chmod 600 /opt/newsroom/deploy/timeweb/.env

${COMPOSE} config
${COMPOSE} up -d --build

for i in $(seq 1 30); do
  st=$(docker inspect --format='{{.State.Health.Status}}' telegram-newsroom 2>/dev/null || echo starting)
  echo "health=${st} (${i}/30)"
  [[ "${st}" == healthy ]] && break
  sleep 5
done

echo "=== docker ps ==="
docker ps -a --filter name=telegram-newsroom
${COMPOSE} ps
curl -sf http://127.0.0.1:8080/health && echo
curl -sf http://127.0.0.1:8080/ready | head -c 400; echo
${COMPOSE} logs --tail=80 newsroom
