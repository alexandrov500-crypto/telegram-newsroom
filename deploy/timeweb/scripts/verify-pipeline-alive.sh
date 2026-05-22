#!/usr/bin/env bash
# 30-second check: is the newsroom scheduler/pipeline alive inside Docker?
# Usage (on VPS): bash deploy/timeweb/scripts/verify-pipeline-alive.sh
set -euo pipefail

CONTAINER="${NEWSROOM_CONTAINER:-telegram-newsroom}"
PORT="${HEALTH_HTTP_PORT:-8080}"

echo "=== 1) Scheduler / pipeline log markers (last 120 lines) ==="
docker logs "$CONTAINER" 2>&1 | tail -120 | grep -E \
  'Scheduler started|job registered: newsroom_pipeline|pipeline execution started|scheduler job executed|scheduler tick skipped|operational_mode=|collector running|collector skipped|scheduler\.pipeline_tick|publish\.attempted' \
  || echo "(no matching lines yet — rebuild image and restart, wait 2 min)"

echo ""
echo "=== 2) Runtime status (scheduler + pipeline stall hint) ==="
if curl -sf "http://127.0.0.1:${PORT}/runtime/status" -o /tmp/newsroom_runtime_status.json 2>/dev/null; then
  python3 - <<'PY'
import json
from pathlib import Path
p = Path("/tmp/newsroom_runtime_status.json")
d = json.loads(p.read_text())
om = d.get("operational_mode") or {}
pl = d.get("pipeline") or {}
act = d.get("activity") or {}
print("operational_mode:", om.get("mode"), "scheduler_allowed:", om.get("scheduler_allowed"))
print("pipeline:", pl)
print("activity:", act)
if om.get("scheduler_allowed") is False:
    print("FAIL: scheduler blocked by operational_mode — set RUNTIME_OPERATIONAL_MODE=production in .env")
elif pl.get("likely_stalled"):
    print("WARN: no recent scheduler tick — check docker logs / rebuild")
else:
    print("OK: scheduler appears active")
PY
else
  echo "WARN: could not reach http://127.0.0.1:${PORT}/runtime/status (is HEALTH_HTTP_PORT published?)"
fi
