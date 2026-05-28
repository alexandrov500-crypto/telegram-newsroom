#!/usr/bin/env bash
# Stop local app.main / stray newsroom Python (Mac). Does not touch VPS Docker.
set -euo pipefail
pkill -f "Python -m app.main" 2>/dev/null || true
pkill -f "python.*-m app.main" 2>/dev/null || true
sleep 1
if pgrep -f "app.main" >/dev/null 2>&1; then
  echo "Some app.main processes still running:"
  pgrep -fl "app.main" || true
  exit 1
fi
echo "No local app.main processes."
