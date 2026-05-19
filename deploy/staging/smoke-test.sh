#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$ROOT"

echo "=== Staging smoke test ==="
python3 -m bot.operations.cli validate-env || true
python3 -m bot.operations.cli smoke
python3 -m bot.operations.cli validate-startup
if [[ -x deploy/staging/health-check.sh ]]; then
  bash deploy/staging/health-check.sh || echo "  [WARN] health-check (stack may be down)"
fi
HEALTH_URL="${STAGING_HEALTH_URL:-http://127.0.0.1:8080/health}"
if command -v curl >/dev/null 2>&1; then
  echo "Health: $HEALTH_URL"
  curl -sf "$HEALTH_URL" >/dev/null && echo "  [PASS] health" || echo "  [FAIL] health"
  curl -sf "${HEALTH_URL%/health}/self-check" >/dev/null 2>&1 && echo "  [PASS] self-check" || echo "  [WARN] self-check (bot may be down)"
  curl -sf "${HEALTH_URL%/health}/startup" >/dev/null 2>&1 && echo "  [PASS] startup" || echo "  [WARN] startup (bot may be down)"
fi
echo "=== Done ==="
