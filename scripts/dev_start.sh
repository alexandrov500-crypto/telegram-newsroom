#!/usr/bin/env bash
# Local DEV only — tests/validation. Does NOT start 24/7 runtime.
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

if [[ "${NEWSROOM_RUNTIME_PROFILE:-}" == "vps" ]]; then
  echo "NEWSROOM_RUNTIME_PROFILE=vps — production runtime is on VPS."
  echo "  make server-status   # remote health"
  echo "  docs/VPS_DEPLOYMENT.md"
fi

if pgrep -f "python.*-m app.main" >/dev/null 2>&1; then
  echo "WARN: app.main is running locally — stop with scripts/stop_local_newsroom.sh"
  echo "      For VPS burn-in, do not run pipeline on Mac."
fi

echo "==> Dev validation (no long-running runtime)"
python3 tools/validate_production_env.py 2>/dev/null || true
python3 -m pytest tests/test_terminal_state_resolver.py tests/test_media_pipeline.py tests/test_autonomous_publish.py -q --tb=no
echo "==> Dev OK. Use 'make server-status' for VPS runtime."
