#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
python3 -c "
from app.config import load_settings
from app.reliability.sqlite_backup import backup_sqlite_database
p = backup_sqlite_database(runtime_dir=load_settings().runtime_state_dir)
print('backup:', p or 'skipped')
"
