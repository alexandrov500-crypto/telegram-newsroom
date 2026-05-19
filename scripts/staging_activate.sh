#!/usr/bin/env bash
# Real-world staging activation — shadow-production newsroom
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

if [[ ! -f .env ]]; then
  cp deploy/staging/env.staging.example .env
  echo "Created .env from staging example — configure Telegram secrets before continuing."
fi
bash scripts/ensure_staging_env.sh

set -a
# shellcheck disable=SC1091
source .env
set +a

export STAGING_MODE="${STAGING_MODE:-true}"
export SHADOW_PUBLISH_ONLY="${SHADOW_PUBLISH_ONLY:-true}"
export AUTO_APPROVAL_ENABLED="${AUTO_APPROVAL_ENABLED:-false}"
export OPS_BURNIN_ENABLED="${OPS_BURNIN_ENABLED:-true}"
export OPS_BURNIN_PROFILE="${OPS_BURNIN_PROFILE:-24h}"
export STAGING_STRICT_STARTUP="${STAGING_STRICT_STARTUP:-true}"

echo "=== Staging activation ==="
echo "  STAGING_MODE=$STAGING_MODE"
echo "  OPS_BURNIN_PROFILE=$OPS_BURNIN_PROFILE"
echo "  SHADOW_PUBLISH_ONLY=$SHADOW_PUBLISH_ONLY"

bash deploy/staging/bootstrap-staging.sh
sleep 8
bash deploy/staging/smoke-test.sh
python3 -m bot.operations.cli validate-feeds
python3 -m bot.operations.cli validate-staging

echo ""
echo "Start operator node: python3 -m bot.main (or docker compose up operator)"
echo "Grafana: http://localhost:3000  Health: http://localhost:8080/ops/"
