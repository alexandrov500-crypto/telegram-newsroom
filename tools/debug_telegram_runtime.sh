#!/usr/bin/env bash
# Operational snapshot for Telegram runtime (VPS or local Docker).
set -euo pipefail

CONTAINER="${NEWSROOM_CONTAINER:-telegram-newsroom}"
HEALTH_URL="${NEWSROOM_HEALTH_URL:-http://127.0.0.1:8080/health}"
OUT="${1:-/tmp/newsroom-telegram-debug.txt}"

{
  echo "=== newsroom telegram runtime debug ==="
  echo "timestamp: $(date -u +%Y-%m-%dT%H:%M:%SZ)"
  echo

  echo "=== docker ps (newsroom) ==="
  docker ps -a --filter "name=${CONTAINER}" --format 'table {{.Names}}\t{{.Status}}\t{{.Image}}\t{{.ID}}' 2>/dev/null || true
  echo

  if docker inspect "${CONTAINER}" >/dev/null 2>&1; then
    echo "=== container inspect ==="
    docker inspect --format='health={{.State.Health.Status}} restarts={{.RestartCount}} started={{.State.StartedAt}}' "${CONTAINER}"
    echo "container_id={{.Id}}" | docker inspect --format='{{.Id}}' "${CONTAINER}"
    echo
  fi

  echo "=== /health JSON ==="
  if command -v curl >/dev/null 2>&1; then
    curl -sf "${HEALTH_URL}" 2>/dev/null | python3 -m json.tool 2>/dev/null || curl -sf "${HEALTH_URL}" || echo "health unreachable"
  else
    echo "curl not installed"
  fi
  echo

  if docker inspect "${CONTAINER}" >/dev/null 2>&1; then
    echo "=== webhook + polling logs (last 80) ==="
    docker logs "${CONTAINER}" 2>&1 | grep -E 'telegram\.(webhook|polling|runtime)|Conflict|getUpdates' | tail -80 || true
    echo

    echo "=== startup / degraded markers ==="
    docker logs "${CONTAINER}" 2>&1 | grep -E 'healthcheck\.degraded|telegram\.runtime\.startup|polling\.disabled' | tail -20 || true
    echo

    echo "=== recent errors (last 30) ==="
    docker logs "${CONTAINER}" 2>&1 | grep -E 'ERROR|Traceback|RuntimeError' | tail -30 || true
  fi

  echo "=== done ==="
} | tee "${OUT}"

echo "written: ${OUT}"
