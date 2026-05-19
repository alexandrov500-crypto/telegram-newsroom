#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$ROOT"

if [[ ! -f .env && -f deploy/staging/env.staging.example ]]; then
  echo "[staging] copy deploy/staging/env.staging.example to .env and configure secrets"
fi

docker compose -f deploy/staging/docker-compose.staging.yml pull postgres redis prometheus grafana tempo 2>/dev/null || true
docker compose -f deploy/staging/docker-compose.staging.yml up -d postgres redis
echo "[staging] waiting for postgres..."
sleep 5
docker compose -f deploy/staging/docker-compose.staging.yml up -d
echo "[staging] cluster starting — operator health on :8080, grafana :3000, prometheus :9090"
