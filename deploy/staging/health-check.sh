#!/usr/bin/env bash
# Curl-based staging infrastructure health validation.
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$ROOT"

HEALTH_URL="${STAGING_HEALTH_URL:-http://127.0.0.1:8080/health}"
PROM_URL="${STAGING_PROMETHEUS_URL:-http://127.0.0.1:9090/-/healthy}"
GRAFANA_URL="${STAGING_GRAFANA_URL:-http://127.0.0.1:3000/api/health}"
TEMPO_URL="${STAGING_TEMPO_URL:-http://127.0.0.1:3200/ready}"
METRICS_URL="${STAGING_METRICS_URL:-http://127.0.0.1:8080/metrics}"

failures=0

check() {
  local name="$1"
  local url="$2"
  if curl -sf --max-time 8 "$url" >/dev/null; then
    echo "  [PASS] $name ($url)"
  else
    echo "  [FAIL] $name ($url)"
    failures=$((failures + 1))
  fi
}

echo "=== Staging health check ==="
check "operator health" "$HEALTH_URL"
check "startup report" "${HEALTH_URL%/health}/startup"
check "reliability snapshot" "${HEALTH_URL%/health}/reliability"
check "self-check" "${HEALTH_URL%/health}/self-check"
check "prometheus" "$PROM_URL"
check "grafana" "$GRAFANA_URL"
check "tempo" "$TEMPO_URL"

if curl -sf --max-time 8 "$METRICS_URL" | grep -q "startup_validation_passed"; then
  echo "  [PASS] startup_validation metric"
else
  echo "  [WARN] startup_validation metric not found (bot may still be starting)"
fi

for pattern in replay_ cognition_ epistemic_; do
  if curl -sf --max-time 8 "$METRICS_URL" | grep -q "$pattern"; then
    echo "  [PASS] metrics prefix $pattern"
  else
    echo "  [WARN] metrics prefix $pattern not yet exported"
  fi
done

if [[ $failures -gt 0 ]]; then
  echo ""
  echo "FAILED: $failures required endpoint(s)"
  exit 1
fi
echo ""
echo "All required endpoints reachable."
