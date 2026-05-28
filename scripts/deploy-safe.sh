#!/usr/bin/env bash
# Safe deploy: preflight, SQLite backup, deploy, health verify.
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "${ROOT}"

LOCK="${ROOT}/var/runtime/deploy.lock"
mkdir -p var/runtime
if [[ -f "${LOCK}" ]]; then
  echo "ERROR: deploy lock present (${LOCK}) — another deploy in progress?" >&2
  exit 1
fi
trap 'rm -f "${LOCK}"' EXIT
date -u +%Y%m%dT%H%M%SZ > "${LOCK}"

echo "==> Preflight"
python3 tools/validate_production_env.py
python3 tools/runtime_preflight.py --runtime-dir "${RUNTIME_STATE_DIR:-var/runtime}" || true

echo "==> SQLite backup"
python3 - <<'PY'
import asyncio
from app.config import load_settings
from app.reliability.sqlite_ops import backup_sqlite_database
from db.session import init_db, close_db

async def main():
    s = load_settings()
    await init_db(s.database_url)
    p = backup_sqlite_database(s, tag="pre_deploy")
    print("backup:", p)
    await close_db()

asyncio.run(main())
PY

TARGET="${1:-deploy/timeweb}"
if [[ -x "${TARGET}/scripts/production-deploy.sh" ]]; then
  echo "==> Deploy (${TARGET})"
  bash "${TARGET}/scripts/production-deploy.sh"
else
  echo "WARN: no production-deploy.sh under ${TARGET}; skip remote deploy"
fi

echo "==> Health"
for i in 1 2 3 4 5 6; do
  if curl -sf "http://127.0.0.1:${HEALTH_HTTP_PORT:-8080}/health" >/tmp/nr_deploy_health.json; then
    python3 -c "import json;d=json.load(open('/tmp/nr_deploy_health.json')); print('status:', d.get('status')); exit(0 if d.get('status')!='unhealthy' else 1)"
    echo "Deploy health OK"
    exit 0
  fi
  sleep 5
done
echo "ERROR: health check failed after deploy" >&2
exit 1
