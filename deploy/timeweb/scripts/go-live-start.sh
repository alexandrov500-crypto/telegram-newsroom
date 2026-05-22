#!/usr/bin/env bash
# Production GO-LIVE: rebuild, start, wait for first pipeline tick, classify status.
# Run on VPS from repo root:
#   bash deploy/timeweb/scripts/go-live-start.sh
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/../../.." && pwd)"
COMPOSE_DIR="$ROOT/deploy/timeweb"
ENV_FILE="$COMPOSE_DIR/.env"

if [[ ! -f "$ENV_FILE" ]]; then
  echo "Missing $ENV_FILE — copy from deploy/timeweb/.env.example and fill secrets." >&2
  exit 1
fi

require_kv() {
  local key="$1"
  if ! grep -qE "^${key}=" "$ENV_FILE"; then
    echo "WARN: $key not set in $ENV_FILE" >&2
  fi
}

echo "=== GO-LIVE preflight (.env) ==="
require_kv RUNTIME_OPERATIONAL_MODE
require_kv DRY_RUN
require_kv PIPELINE_INTERVAL_MINUTES
require_kv TARGET_CHANNEL_ID
require_kv TELEGRAM_API_ID
require_kv TELEGRAM_API_HASH

MODE="$(grep -E '^RUNTIME_OPERATIONAL_MODE=' "$ENV_FILE" | cut -d= -f2- | tr -d ' \"' || true)"
DRY="$(grep -E '^DRY_RUN=' "$ENV_FILE" | cut -d= -f2- | tr -d ' \"' || true)"
if [[ "${MODE,,}" != "production" && "${MODE,,}" != "first_post_debug" && "${MODE,,}" != "degraded" ]]; then
  echo "FAIL: RUNTIME_OPERATIONAL_MODE must be production (or first_post_debug for first post). Got: ${MODE:-<unset>}" >&2
  exit 1
fi
if [[ "${DRY,,}" == "true" || "${DRY,,}" == "1" ]]; then
  echo "FAIL: DRY_RUN must be false for GO-LIVE." >&2
  exit 1
fi

# Sync persisted mode on volume before start (compose sets RUNTIME_STATE_DIR=/data/runtime)
RT_DIR="${NEWSROOM_HOST_DATA:-/opt/newsroom/data}/runtime"
if [[ -d "$RT_DIR" ]]; then
  echo '{"mode":"'"${MODE:-production}"'","updated_at":"'"$(date -u +%Y-%m-%dT%H:%M:%SZ)"'","reason":"go_live_start"}' \
    > "$RT_DIR/operational_mode.json" 2>/dev/null || true
  echo "Wrote $RT_DIR/operational_mode.json mode=${MODE:-production}"
fi

echo ""
echo "=== Rebuild + start (deploy/timeweb) ==="
cd "$COMPOSE_DIR"
make rebuild

echo ""
echo "=== Waiting 90s for bootstrap + first scheduler tick ==="
sleep 90

bash "$ROOT/deploy/timeweb/scripts/go-live-verify.sh"
