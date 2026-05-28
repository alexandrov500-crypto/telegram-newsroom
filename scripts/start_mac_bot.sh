#!/usr/bin/env bash
# Mac-only: stop VPS container first, then start newsroom locally.
# Production burn-in should run on VPS — set NEWSROOM_RUNTIME_PROFILE=vps to block local starts.
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "${ROOT}"

if [[ "${NEWSROOM_RUNTIME_PROFILE:-}" == "vps" && "${LOCAL_RUNTIME_ALLOWED:-false}" != "true" ]]; then
  echo "ERROR: Local runtime disabled (NEWSROOM_RUNTIME_PROFILE=vps)."
  echo "  Burn-in runs on VPS — see docs/VPS_DEPLOYMENT.md"
  echo "  Emergency local: LOCAL_RUNTIME_ALLOWED=true $0"
  exit 1
fi

echo "==> Stopping old local app.main"
bash "${ROOT}/scripts/stop_local_newsroom.sh" 2>/dev/null || true
pkill -9 -f "python.*-m app.main" 2>/dev/null || true
sleep 1

if command -v docker >/dev/null 2>&1; then
  if docker ps --format '{{.Names}}' 2>/dev/null | grep -qx 'telegram-newsroom'; then
    echo "WARN: VPS container telegram-newsroom is still running — bot polling will conflict."
    echo "      On VPS run: docker stop telegram-newsroom"
  fi
fi

mkdir -p data var/runtime var/runtime/media_cache logs
export NEWSROOM_GIT_SHA="${NEWSROOM_GIT_SHA:-$(git -C "${ROOT}" rev-parse HEAD 2>/dev/null || echo unknown)}"
export NEWSROOM_BUILD_TIMESTAMP="${NEWSROOM_BUILD_TIMESTAMP:-$(date -u +%Y-%m-%dT%H:%M:%SZ)}"
export PIPELINE_BOOTSTRAP_ON_START="${PIPELINE_BOOTSTRAP_ON_START:-false}"
export DESK_MIN_QUALITY_SCORE="${DESK_MIN_QUALITY_SCORE:-45}"
export DESK_LOWER_PRIORITY_SCORE="${DESK_LOWER_PRIORITY_SCORE:-32}"
export DESK_MIN_MACRO_MARKET_SCORE="${DESK_MIN_MACRO_MARKET_SCORE:-30}"
export MIN_RAW_POSTS_FOR_AI="${MIN_RAW_POSTS_FOR_AI:-1}"
export SUMMARY_STYLE="${SUMMARY_STYLE:-warm-overview}"

echo "==> Validate .env"
python3 tools/validate_production_env.py

echo "==> Start bot (logs: logs/local-run.log)"
: > logs/local-run.log
nohup python3 -m app.main >> logs/local-run.log 2>&1 &
echo "PID=$!"
sleep 12
if curl -sf http://127.0.0.1:8080/health >/tmp/nr_health.json 2>/dev/null; then
  python3 - <<'PY'
import json
d = json.load(open("/tmp/nr_health.json"))
tg = d.get("dependencies", {}).get("telegram_api", {})
print("status:", d.get("status"))
print("telegram:", tg.get("status"), (tg.get("detail") or "")[:90])
print("ai:", d.get("ai_pipeline_enabled"), "collector:", d.get("collector_enabled"))
if tg.get("conflict_detected"):
    print("\nACTION: docker stop telegram-newsroom  # on VPS")
PY
else
  echo "Health not ready yet — tail logs/local-run.log"
fi
