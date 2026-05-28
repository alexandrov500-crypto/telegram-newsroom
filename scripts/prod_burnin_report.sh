#!/usr/bin/env bash
set -euo pipefail
HOST="${VPS_HOST:?Set VPS_HOST}"
USER="${VPS_USER:-ubuntu}"
DIR="${VPS_DEPLOY_DIR:-/opt/newsroom/app/deploy/timeweb}"
ssh "${USER}@${HOST}" "cd '${DIR}' && docker compose exec -T newsroom bash scripts/burnin-check.sh"
