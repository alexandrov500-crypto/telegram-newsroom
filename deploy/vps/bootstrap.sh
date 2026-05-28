#!/usr/bin/env bash
# VPS host bootstrap (run once on Ubuntu 24.04).
set -euo pipefail

echo "==> Docker"
if ! command -v docker >/dev/null 2>&1; then
  sudo apt-get update -y
  sudo apt-get install -y docker.io docker-compose-plugin git curl
  sudo usermod -aG docker "$USER" || true
  echo "Log out and back in for docker group, then re-run."
fi

BASE="${NEWSROOM_BASE:-/opt/newsroom}"
echo "==> Directories under ${BASE}"
sudo mkdir -p "${BASE}/data" "${BASE}/logs" "${BASE}/sessions" "${BASE}/backups" "${BASE}/app"
sudo chown -R "${USER}:${USER}" "${BASE}"

echo "==> Logrotate + systemd (bare-metal, optional)"
echo "  sudo cp deploy/logrotate/newsroom /etc/logrotate.d/newsroom"
echo "  sudo cp deploy/systemd/newsroom.service /etc/systemd/system/"

echo "==> Next"
echo "  1. Clone repo into ${BASE}/app"
echo "  2. cd ${BASE}/app/deploy/timeweb && cp .env.example .env"
echo "  3. make up && make health"
