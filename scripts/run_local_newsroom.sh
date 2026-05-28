#!/usr/bin/env bash
# Start autonomous newsroom locally (app.main: collector + scheduler + bot polling).
# Stop VPS Docker with the same BOT_TOKEN before running, or set SEND_STARTUP_NOTIFICATION=false in .env.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "${ROOT}"

pick_python() {
  local c
  for c in "${ROOT}/.venv/bin/python" python3; do
    if command -v "${c}" >/dev/null 2>&1 && "${c}" -c "import sqlalchemy, aiogram" 2>/dev/null; then
      echo "${c}"
      return 0
    fi
  done
  return 1
}

if ! PYTHON="$(pick_python)"; then
  echo "FAIL: no Python with sqlalchemy+aiogram (.venv broken? try: python3 -m pip install -r requirements.txt)" >&2
  exit 1
fi

mkdir -p data var/runtime var/runtime/media_cache data/sessions logs

echo "==> Using ${PYTHON}"
echo "==> Validating .env"
"${PYTHON}" tools/validate_production_env.py

echo "==> Preflight (settings + DB migrate)"
"${PYTHON}" - <<'PY'
import asyncio
from app.config import load_settings
from app.startup_validation import validate_settings_for_launch, warn_duplicate_runtime_startup_risk
from db.session import close_db, init_db

async def main() -> None:
    s = load_settings()
    validate_settings_for_launch(s)
    warn_duplicate_runtime_startup_risk(s)
    await init_db(s.database_url, pool_size=s.database_pool_size, max_overflow=s.database_max_overflow)
    await close_db()
    import os

    print(
        "OK  operational_mode=%s interval_min=%s polling=%s dry_run=%s runtime_dir=%s"
        % (
            os.getenv("RUNTIME_OPERATIONAL_MODE", "production"),
            s.pipeline_interval_minutes,
            s.telegram_polling_enabled,
            s.dry_run,
            s.runtime_state_dir,
        )
    )
    print("OK  database_url=%s" % (s.database_url,))

asyncio.run(main())
PY

echo "==> Mac-only: stop VPS bot first or polling will conflict:"
echo "    ssh root@YOUR_VPS 'docker stop telegram-newsroom'"
echo "==> Starting python -m app.main (Ctrl+C to stop)"
exec "${PYTHON}" -m app.main
