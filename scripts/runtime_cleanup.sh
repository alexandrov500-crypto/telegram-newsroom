#!/usr/bin/env bash
# Prune old media cache + oversized local logs (safe for dev workstation).
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
RT="${RUNTIME_STATE_DIR:-$ROOT/var/runtime}"
DAYS="${MEDIA_CACHE_RETENTION_DAYS:-14}"
echo "==> Media cache older than ${DAYS}d"
find "${RT}/media_cache" -type f -mtime +"${DAYS}" -delete 2>/dev/null || true
echo "==> Truncate local-run.log if >50MB"
LOG="$ROOT/logs/local-run.log"
if [[ -f "$LOG" ]]; then
  sz=$(stat -f%z "$LOG" 2>/dev/null || stat -c%s "$LOG" 2>/dev/null || echo 0)
  if [[ "$sz" -gt 52428800 ]]; then
    tail -n 5000 "$LOG" > "${LOG}.tmp" && mv "${LOG}.tmp" "$LOG"
    echo "truncated $LOG"
  fi
fi
echo "done"
