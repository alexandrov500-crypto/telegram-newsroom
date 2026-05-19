#!/usr/bin/env bash
# Production health verification — curl + metric smoke.
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$ROOT"

BASE="${PRODUCTION_HEALTH_URL:-http://127.0.0.1:8080}"
failures=0

check() {
  local name="$1"
  local path="$2"
  local url="${BASE}${path}"
  if curl -sf --max-time 10 "$url" >/dev/null; then
    echo "  [PASS] $name"
  else
    echo "  [FAIL] $name ($url)"
    failures=$((failures + 1))
  fi
}

echo "=== Production health verification ==="
check "liveness" "/health"
check "readiness" "/ready"
check "startup" "/startup"
check "go_live" "/go_live"
check "safety" "/safety"
check "reliability" "/reliability"
check "live_ops" "/live_ops"
check "platform" "/platform"
check "ops_playbook" "/ops_playbook"
check "live_deploy" "/live_deploy"
check "week1" "/week1"

echo ""
echo "--- Sample outputs (truncated) ---"
echo "/go_live:"
curl -sf --max-time 10 "${BASE}/go_live" 2>/dev/null | head -c 400 || echo "  (unavailable)"
echo ""
echo "/live_ops:"
curl -sf --max-time 10 "${BASE}/live_ops" 2>/dev/null | head -c 400 || echo "  (unavailable)"

if curl -sf --max-time 10 "${BASE}/metrics" | grep -qE 'queue_|publish_|cognition_'; then
  echo "  [PASS] core metrics exported"
else
  echo "  [WARN] metrics prefixes not yet visible"
fi

echo ""
echo "Telegram operator commands:"
echo "  /startup_check /production_ready /channel_status"
echo "  /go_live_check /safety_status /queues_live"
echo "  /first_publication_status"

if [[ $failures -gt 0 ]]; then
  echo ""
  echo "FAILED: $failures endpoint(s)"
  exit 1
fi
echo ""
echo "All required endpoints reachable."
