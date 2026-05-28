#!/usr/bin/env bash
set -euo pipefail
HOST="${VPS_HOST:?Set VPS_HOST}"
USER="${VPS_USER:-ubuntu}"
DIR="${VPS_DEPLOY_DIR:-/opt/newsroom/app/deploy/timeweb}"
ssh "${USER}@${HOST}" "cd '${DIR}' && docker compose restart newsroom && sleep 8 && curl -sf http://127.0.0.1:8080/health | head -c 400"
echo ""
echo "Restart complete."
