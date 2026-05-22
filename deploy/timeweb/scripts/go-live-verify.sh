#!/usr/bin/env bash
# Production go-live verification: classify runtime as ACTIVE / PARTIAL / IDLE / BROKEN.
# Usage: bash deploy/timeweb/scripts/go-live-verify.sh
set -euo pipefail

CONTAINER="${NEWSROOM_CONTAINER:-telegram-newsroom}"
PORT="${HEALTH_HTTP_PORT:-8080}"
LOG_TAIL="${GO_LIVE_LOG_TAIL:-400}"

echo "=== Newsroom go-live verification ==="
echo "container=$CONTAINER health_port=$PORT"

LOG=$(docker logs "$CONTAINER" 2>&1 | tail -"$LOG_TAIL" || true)

has() { echo "$LOG" | grep -qE "$1"; }

SCHED_STARTED=0
JOB_REG=0
JOB_EXEC=0
PIPE_START=0
TICK_DONE=0
COLLECT=0
DRAFT=0
PUBLISH_OK=0
MODE_BLOCK=0
STALLED=1

has 'Scheduler started' && SCHED_STARTED=1
has 'job registered: newsroom_pipeline' && JOB_REG=1
has 'scheduler job executed: newsroom_pipeline' && JOB_EXEC=1
has 'pipeline execution started' && PIPE_START=1
has 'pipeline tick completed:' && TICK_DONE=1
has 'collector running|collector finished:' && COLLECT=1
has 'draft generated:' && DRAFT=1
has 'publish succeeded:' && PUBLISH_OK=1
has 'scheduler tick skipped: operational_mode=' && MODE_BLOCK=1

STATUS_JSON=""
if curl -sf "http://127.0.0.1:${PORT}/runtime/status" -o /tmp/newsroom_golive_status.json 2>/dev/null; then
  STATUS_JSON=$(cat /tmp/newsroom_golive_status.json)
  STALLED=$(python3 - <<'PY'
import json
d=json.load(open("/tmp/newsroom_golive_status.json"))
print(1 if (d.get("pipeline") or {}).get("likely_stalled") else 0)
PY
)
fi

CLASS="BROKEN"
if [[ "$MODE_BLOCK" -eq 1 ]]; then
  CLASS="BROKEN"
elif [[ "$SCHED_STARTED" -eq 0 || "$JOB_REG" -eq 0 ]]; then
  CLASS="BROKEN"
elif [[ "$PIPE_START" -eq 0 && "$JOB_EXEC" -eq 0 ]]; then
  CLASS="IDLE"
elif [[ "$PUBLISH_OK" -eq 1 && "$DRAFT" -eq 1 ]]; then
  CLASS="ACTIVE"
elif [[ "$TICK_DONE" -eq 1 ]]; then
  CLASS="PARTIAL"
else
  CLASS="IDLE"
fi

echo ""
echo "=== Signals ==="
printf "  scheduler_started=%s job_registered=%s job_executed=%s\n" "$SCHED_STARTED" "$JOB_REG" "$JOB_EXEC"
printf "  pipeline_started=%s tick_completed=%s mode_blocked=%s\n" "$PIPE_START" "$TICK_DONE" "$MODE_BLOCK"
printf "  collector=%s draft=%s publish_ok=%s runtime_stalled=%s\n" "$COLLECT" "$DRAFT" "$PUBLISH_OK" "$STALLED"
echo ""
echo "=== CLASSIFICATION: $CLASS ==="

case "$CLASS" in
  ACTIVE)
    echo "GO-LIVE READY: autonomous pipeline ran and published."
    ;;
  PARTIAL)
    echo "OPERATING PARTIALLY: ticks run but no publish yet — check summarize_idle in logs (pipeline tick completed)."
    echo "  Hint: enable first_post_debug + FORCE_SINGLE_PUBLISH for first post, or wait for new source messages."
    ;;
  IDLE)
    echo "IDLE: process up but pipeline not executing — rebuild image, set RUNTIME_OPERATIONAL_MODE=production, restart."
    ;;
  BROKEN)
    echo "BROKEN: scheduler blocked or not initialized — fix operational_mode / redeploy latest image."
    ;;
esac

echo ""
echo "=== Recent pipeline markers ==="
echo "$LOG" | grep -E \
  'Scheduler started|job registered|pipeline execution|scheduler job executed|pipeline tick completed|pipeline idle at|draft generated|publish succeeded|operational_mode=' \
  | tail -30 || echo "(none)"

if [[ -n "$STATUS_JSON" ]]; then
  echo ""
  echo "=== /runtime/status pipeline section ==="
  python3 - <<'PY'
import json
d=json.load(open("/tmp/newsroom_golive_status.json"))
print(json.dumps({
  "operational_mode": d.get("operational_mode"),
  "pipeline": d.get("pipeline"),
  "activity": d.get("activity"),
}, indent=2))
PY
fi

[[ "$CLASS" == "ACTIVE" ]] && exit 0
[[ "$CLASS" == "PARTIAL" ]] && exit 2
exit 1
