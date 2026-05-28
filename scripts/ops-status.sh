#!/usr/bin/env bash
# Operator status: health components + runtime report.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
PORT="${HEALTH_HTTP_PORT:-8080}"
echo "==> Health components"
for p in /health/components /health/runtime /health/pipeline /health/telegram /health/openai; do
  code=$(curl -s -o /tmp/nr_health.json -w "%{http_code}" "http://127.0.0.1:${PORT}${p}" 2>/dev/null || echo "000")
  echo "  ${p} HTTP ${code}"
done
echo ""
echo "==> Runtime report"
python3 -c "
from app.config import load_settings
from app.observability.runtime_report import write_runtime_report
p = write_runtime_report(load_settings())
print(p)
"
echo ""
echo "==> PUBLIC GO check"
python3 tools/public_go_check.py
