#!/usr/bin/env bash
# Remote VPS status (SSH). Set VPS_HOST, VPS_USER, VPS_DEPLOY_DIR.
set -euo pipefail
HOST="${VPS_HOST:?Set VPS_HOST}"
USER="${VPS_USER:-ubuntu}"
DIR="${VPS_DEPLOY_DIR:-/opt/newsroom/app/deploy/timeweb}"
PORT="${VPS_HEALTH_PORT:-8080}"

ssh "${USER}@${HOST}" bash -s <<REMOTE
set -euo pipefail
cd "${DIR}"
echo "==> Docker"
docker ps --filter name=telegram-newsroom --format 'table {{.Names}}\t{{.Status}}\t{{.Ports}}' || true
echo ""
echo "==> Health"
curl -sf "http://127.0.0.1:${PORT}/health/components" | python3 -m json.tool 2>/dev/null || echo "health unreachable"
echo ""
echo "==> Runtime report"
docker compose exec -T newsroom python3 -c "
from app.config import load_settings
from app.observability.runtime_report import write_runtime_report
print(write_runtime_report(load_settings()))
" 2>/dev/null || echo "report skipped"
REMOTE
