#!/usr/bin/env bash
# Restore SQLite from backup path. Stops nothing — run when runtime is down.
set -euo pipefail
SRC="${1:?Usage: restore.sh /path/to/newsroom_*.db}"
DEST="${NEWSROOM_DB_DEST:-./data/newsroom.db}"
if [[ ! -f "$SRC" ]]; then
  echo "Backup not found: $SRC"
  exit 1
fi
mkdir -p "$(dirname "$DEST")"
cp -a "$DEST" "${DEST}.pre-restore.$(date +%s)" 2>/dev/null || true
cp -a "$SRC" "$DEST"
echo "Restored $SRC -> $DEST"
