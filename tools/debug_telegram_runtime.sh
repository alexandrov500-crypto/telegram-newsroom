#!/usr/bin/env bash
# Incident bundle: Telegram runtime, health, version, logs (no secrets).
set -euo pipefail

CONTAINER="${NEWSROOM_CONTAINER:-telegram-newsroom}"
HEALTH_URL="${NEWSROOM_HEALTH_URL:-http://127.0.0.1:8080/health}"
VERSION_URL="${NEWSROOM_VERSION_URL:-http://127.0.0.1:8080/version}"
TS="$(date -u +%Y%m%dT%H%M%SZ)"
WORKDIR="${TMPDIR:-/tmp}/newsroom-incident-${TS}"
ARCHIVE="${1:-/tmp/newsroom-incident-${TS}.tar.gz}"

mkdir -p "${WORKDIR}"

_log() { echo "$*" | tee -a "${WORKDIR}/summary.txt"; }

_log "=== newsroom incident bundle ${TS} ==="

{
  echo "=== docker ps ==="
  docker ps -a --filter "name=${CONTAINER}" --no-trunc 2>/dev/null || true
  echo
  if docker inspect "${CONTAINER}" >/dev/null 2>&1; then
    echo "=== docker inspect ==="
    docker inspect "${CONTAINER}" 2>/dev/null || true
    echo
    echo "=== restart count ==="
    docker inspect --format='health={{.State.Health.Status}} restarts={{.RestartCount}} started={{.State.StartedAt}}' "${CONTAINER}" 2>/dev/null || true
    echo
  fi
} > "${WORKDIR}/docker.txt" 2>&1

if command -v curl >/dev/null 2>&1; then
  curl -sf "${HEALTH_URL}" -o "${WORKDIR}/health.json" 2>/dev/null || echo '{"error":"health_unreachable"}' > "${WORKDIR}/health.json"
  curl -sf "${VERSION_URL}" -o "${WORKDIR}/version.json" 2>/dev/null || echo '{"error":"version_unreachable"}' > "${WORKDIR}/version.json"
else
  echo '{"error":"curl_missing"}' > "${WORKDIR}/health.json"
  echo '{"error":"curl_missing"}' > "${WORKDIR}/version.json"
fi

if docker inspect "${CONTAINER}" >/dev/null 2>&1; then
  docker logs "${CONTAINER}" 2>&1 | tail -300 > "${WORKDIR}/logs_tail.txt" || true
  docker logs "${CONTAINER}" 2>&1 | grep -E 'telegram\.(webhook|polling|runtime)|runtime\.(shutdown|slo)|healthcheck|Conflict|degraded' | tail -120 > "${WORKDIR}/logs_filtered.txt" || true

  docker exec "${CONTAINER}" python -c "
import json, os
from app.build_provenance import load_build_provenance, version_payload
from app.dependency_state import get_dependency_state
from app.runtime_metrics import export_merged_metrics
prov = load_build_provenance()
deps = get_dependency_state()
whitelist = sorted(k for k in os.environ if k.startswith(('NEWSROOM_', 'HEALTH_', 'TELEGRAM_', 'OPENAI_', 'RUNTIME_', 'GIT_', 'BUILD_', 'DATABASE_', 'BOT_', 'ADMIN_')))
print(json.dumps({
  'build': prov.to_dict(),
  'version': version_payload(polling_instance_id=deps.polling_instance_id),
  'metrics': export_merged_metrics(),
  'env_whitelist': {k: os.environ.get(k, '')[:80] for k in whitelist},
}, indent=2))
" > "${WORKDIR}/runtime_in_container.json" 2>/dev/null || echo '{}' > "${WORKDIR}/runtime_in_container.json"

  docker exec "${CONTAINER}" python -c "
import asyncio, time
from app.config import load_settings
from app.telegram_bot import create_newsroom_bot
async def probe():
    t0 = time.perf_counter()
    s = load_settings()
    bot = create_newsroom_bot(s)
    try:
        me = await bot.get_me()
        wh = await bot.get_webhook_info()
        return {'ok': True, 'duration_sec': round(time.perf_counter()-t0, 4), 'bot_id': me.id, 'webhook_url': wh.url or ''}
    except Exception as e:
        return {'ok': False, 'duration_sec': round(time.perf_counter()-t0, 4), 'error': repr(e)[:400]}
    finally:
        await bot.session.close()
asyncio.run(probe())
" > "${WORKDIR}/network_probe.json" 2>/dev/null || echo '{"error":"probe_failed"}' > "${WORKDIR}/network_probe.json"
fi

{
  echo "=== health ==="
  cat "${WORKDIR}/health.json" 2>/dev/null | python3 -m json.tool 2>/dev/null || cat "${WORKDIR}/health.json"
  echo
  echo "=== version ==="
  cat "${WORKDIR}/version.json" 2>/dev/null | python3 -m json.tool 2>/dev/null || cat "${WORKDIR}/version.json"
} >> "${WORKDIR}/summary.txt" 2>&1

tar -czf "${ARCHIVE}" -C "$(dirname "${WORKDIR}")" "$(basename "${WORKDIR}")"
_log "archive: ${ARCHIVE}"
_log "workdir: ${WORKDIR}"
