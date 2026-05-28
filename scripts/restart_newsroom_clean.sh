#!/usr/bin/env bash
# Stop all local newsroom processes and start a single fresh runtime (Mac).
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

echo "== Stopping local newsroom =="
bash "$ROOT/scripts/stop_local_newsroom.sh" || true

echo "== Checking for leftover app.main =="
if pgrep -fl "app.main" 2>/dev/null; then
  echo "WARNING: app.main still running — kill manually or stop VPS duplicate"
  pgrep -fl "app.main" || true
else
  echo "No app.main processes."
fi

echo "== Verify transport tests (quick) =="
python3 -m pytest tests/test_telegram_transport.py tests/test_publisher.py -q --tb=no

echo "== Starting newsroom =="
bash "$ROOT/scripts/start_mac_bot.sh"

echo "== Health (staging) =="
sleep 3
curl -sf "http://127.0.0.1:${HEALTH_PORT:-8080}/health" | python3 -c "
import json,sys
d=json.load(sys.stdin)
s=d.get('staging') or {}
print('launch_ready', s.get('launch_ready'))
print('transport_layer_ok', s.get('transport_layer_ok'))
print('alerts', s.get('alerts'))
" || echo "Health not ready yet — wait and curl /health"
