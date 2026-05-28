#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

mkdir -p "${ROOT}/var/runtime" "${ROOT}/var/backups" "${ROOT}/var/log" "${ROOT}/var/reports"
echo "[bootstrap] runtime directories: ${ROOT}/var/"

if [[ ! -f "${ROOT}/.env" && -f "${ROOT}/.env.example" ]]; then
  echo "[bootstrap] hint: copy .env.example to .env and fill secrets"
fi

if command -v python3 >/dev/null 2>&1; then
  echo "[bootstrap] python3: $(python3 --version)"
  python3 - <<PY || true
import os
import sys
from pathlib import Path
root = Path("${ROOT}")
sys.path.insert(0, str(root))
try:
    from app.config_diagnostics import missing_env_for_bootstrap
    m = missing_env_for_bootstrap()
    if m:
        print("[bootstrap] missing env for full app:", ", ".join(m))
    else:
        print("[bootstrap] required env keys present (quick scan)")
except Exception as e:
    print("[bootstrap] env scan skipped:", e)
PY
fi

echo "[bootstrap] done."
echo "[bootstrap] Local dev:  bash scripts/dev_start.sh"
echo "[bootstrap] VPS deploy: docs/VPS_DEPLOYMENT.md + deploy/timeweb/make up"
