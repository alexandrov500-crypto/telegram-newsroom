#!/usr/bin/env bash
# Run ON VPS: cd /opt/newsroom && bash deploy/timeweb/scripts/production-deploy.sh
set -euo pipefail

REPO_ROOT="${REPO_ROOT:-/opt/newsroom}"
BRANCH="${BRANCH:-main}"
COMPOSE_DIR="${REPO_ROOT}/deploy/timeweb"

log() { echo "[deploy] $*"; }
die() { echo "[deploy] ERROR: $*" >&2; exit 1; }

command -v docker >/dev/null || die "docker not installed"
docker compose version >/dev/null 2>&1 || die "docker compose plugin required"

cd "${REPO_ROOT}"
log "repo=${REPO_ROOT} branch=${BRANCH}"

git fetch origin --prune || true
git checkout "${BRANCH}"
git pull --ff-only origin "${BRANCH}" 2>/dev/null || git reset --hard "origin/${BRANCH}"

mkdir -p "${REPO_ROOT}/data/runtime" "${REPO_ROOT}/data/backups" \
  "${REPO_ROOT}/logs" "${REPO_ROOT}/sessions"
chown -R 1000:1000 "${REPO_ROOT}/data" "${REPO_ROOT}/logs" "${REPO_ROOT}/sessions" 2>/dev/null || true
chmod 700 "${REPO_ROOT}/sessions" 2>/dev/null || true

cd "${COMPOSE_DIR}"
[[ -f .env ]] || { cp .env.example .env && chmod 600 .env; }

set_env_kv() {
  local key="$1" val="$2"
  [[ -z "${val}" ]] && return 0
  if grep -q "^${key}=" .env; then
    sed -i.bak "s|^${key}=.*|${key}=${val}|" .env
  else
    echo "${key}=${val}" >> .env
  fi
}

set_env_kv OPENAI_API_KEY "${OPENAI_API_KEY:-}"
set_env_kv TELEGRAM_API_ID "${TELEGRAM_API_ID:-}"
set_env_kv TELEGRAM_API_HASH "${TELEGRAM_API_HASH:-}"
set_env_kv BOT_TOKEN "${BOT_TOKEN:-}"
set_env_kv TELETHON_SESSION_STRING "${TELETHON_SESSION_STRING:-}"
set_env_kv ADMIN_USER_ID "${ADMIN_USER_ID:-}"
set_env_kv TARGET_CHANNEL_ID "${TARGET_CHANNEL_ID:-}"
set_env_kv SOURCE_CHANNELS "${SOURCE_CHANNELS:-}"
set_env_kv RUNTIME_OPERATIONAL_MODE "${RUNTIME_OPERATIONAL_MODE:-production}"
set_env_kv DRY_RUN "${DRY_RUN:-false}"
set_env_kv PIPELINE_BOOTSTRAP_ON_START "${PIPELINE_BOOTSTRAP_ON_START:-true}"

env_val() { grep "^$1=" .env 2>/dev/null | cut -d= -f2- || true; }

is_placeholder() {
  case "$1" in
    *replace*|*REPLACE*|123456789:*) return 0 ;;
    12345678|123456789) return 0 ;;
    "") return 0 ;;
  esac
  return 1
}

missing=()
for k in OPENAI_API_KEY TELEGRAM_API_ID TELEGRAM_API_HASH BOT_TOKEN ADMIN_USER_ID TARGET_CHANNEL_ID SOURCE_CHANNELS; do
  v=$(env_val "$k")
  if is_placeholder "$v"; then missing+=("$k"); fi
done

if [[ ${#missing[@]} -gt 0 ]]; then
  die "incomplete .env — edit: ${COMPOSE_DIR}/.env missing: ${missing[*]}"
fi

if [[ -z "$(env_val TELETHON_SESSION_STRING)" && ! -f "${REPO_ROOT}/sessions/telethon.session" ]]; then
  die "set TELETHON_SESSION_STRING in .env or add ${REPO_ROOT}/sessions/telethon.session"
fi

set_env_kv EDITORIAL_ZERO_HUMAN_IN_LOOP "${EDITORIAL_ZERO_HUMAN_IN_LOOP:-true}"
set_env_kv UEOS_PUBLISH_THRESHOLD "${UEOS_PUBLISH_THRESHOLD:-72}"
set_env_kv UEOS_DIGEST_THRESHOLD "${UEOS_DIGEST_THRESHOLD:-55}"
set_env_kv EGDL_REQUIRE_MULTI_SOURCE_CLASS "${EGDL_REQUIRE_MULTI_SOURCE_CLASS:-false}"
set_env_kv EGDL_GRAVITY_REJECT "${EGDL_GRAVITY_REJECT:-30}"
set_env_kv EDITORIAL_GROWTH_INTEL_SOFT_QUALITY "${EDITORIAL_GROWTH_INTEL_SOFT_QUALITY:-48}"
set_env_kv EAA_MIN_AUTONOMY_CONFIDENCE "${EAA_MIN_AUTONOMY_CONFIDENCE:-0.62}"

COMPOSE_FILE="${COMPOSE_DIR}/docker-compose.yml"
COMPOSE_NETWORK="telegram-newsroom-timeweb_default"
COMPOSE_SERVICE="newsroom"
COMPOSE_IMAGE="telegram-newsroom:timeweb-production"

ensure_compose_network() {
  if ! docker network inspect "${COMPOSE_NETWORK}" >/dev/null 2>&1; then
    log "creating compose network ${COMPOSE_NETWORK}"
    docker network create "${COMPOSE_NETWORK}" >/dev/null 2>&1 || true
  fi
}

run_newsroom_fallback() {
  local compose_env="${COMPOSE_DIR}/.env"
  log "compose up failed — starting ${COMPOSE_SERVICE} via docker run (shared network with xray/y2o)"
  ensure_compose_network
  docker run -d \
    --name telegram-newsroom \
    --restart unless-stopped \
    --stop-timeout 45 \
    --network "${COMPOSE_NETWORK}" \
    --env-file "${compose_env}" \
    -e TZ="${TZ:-UTC}" \
    -e DATABASE_URL=sqlite+aiosqlite:////data/newsroom.db \
    -e RUNTIME_STATE_DIR=/data/runtime \
    -e NEWSROOM_GLOBAL_LOCK_DIR=/data/runtime/locks \
    -e NEWSROOM_LOCK_BY_BOT_TOKEN=true \
    -e SEND_STARTUP_NOTIFICATION=false \
    -e NEWSROOM_BACKUP_DIR=/data/backups \
    -e TELETHON_SESSION_PATH=/data/sessions/telethon.session \
    -e HEALTH_HTTP_PORT=8080 \
    -e HEALTH_HTTP_BIND=0.0.0.0 \
    -v "${REPO_ROOT}/data:/data" \
    -v "${REPO_ROOT}/logs:/data/logs" \
    -v "${REPO_ROOT}/sessions:/data/sessions" \
    -v "${compose_env}:/app/.env" \
    -p 127.0.0.1:8080:8080 \
    --health-cmd "python /app/docker/http_ready_probe.py" \
    --health-interval 60s \
    --health-timeout 20s \
    --health-start-period 180s \
    --health-retries 3 \
    "${COMPOSE_IMAGE}"
}

shared_network_sidecars_present() {
  docker network inspect "${COMPOSE_NETWORK}" --format '{{range .Containers}}{{.Name}} {{end}}' 2>/dev/null \
    | grep -qE '(^| )(xray|y2o)( |$)'
}

recreate_newsroom_only() {
  log "docker compose config"
  docker compose -f "${COMPOSE_FILE}" config >/dev/null

  log "docker compose build ${COMPOSE_SERVICE} (no full-stack recreate)"
  docker compose -f "${COMPOSE_FILE}" build "${COMPOSE_SERVICE}"

  log "stop/remove ${COMPOSE_SERVICE} container only (preserve network for xray/y2o)"
  docker stop telegram-newsroom 2>/dev/null || true
  docker rm telegram-newsroom 2>/dev/null || true

  ensure_compose_network

  if shared_network_sidecars_present; then
    log "xray/y2o detected on ${COMPOSE_NETWORK} — using docker run (compose skips network teardown)"
    run_newsroom_fallback
    return 0
  fi

  log "docker compose up -d --no-deps --force-recreate ${COMPOSE_SERVICE}"
  if ! docker compose -f "${COMPOSE_FILE}" up -d --no-deps --force-recreate "${COMPOSE_SERVICE}"; then
    run_newsroom_fallback
  fi
}

if [[ -f "${REPO_ROOT}/data/newsroom.db" ]]; then
  cp "${REPO_ROOT}/data/newsroom.db" \
    "${REPO_ROOT}/data/backups/newsroom.db.bak.$(date +%Y%m%d-%H%M%S)" || true
fi

RT_DIR="${NEWSROOM_HOST_DATA:-/opt/newsroom/data}/runtime"
mkdir -p "$RT_DIR"
echo '{"mode":"production","updated_at":"'"$(date -u +%Y-%m-%dT%H:%M:%SZ)"'","reason":"production_deploy"}' \
  > "$RT_DIR/operational_mode.json" 2>/dev/null || true

recreate_newsroom_only

for i in $(seq 1 30); do
  st=$(docker inspect --format='{{.State.Health.Status}}' telegram-newsroom 2>/dev/null || echo "starting")
  log "health check ${i}/30: ${st}"
  [[ "${st}" == "healthy" ]] && break
  sleep 5
done

echo "========== docker ps =========="
docker ps -a --filter name=telegram-newsroom

echo "========== compose ps =========="
docker compose -f docker-compose.yml ps

echo "========== curl health =========="
curl -sf "http://127.0.0.1:8080/health"; echo
curl -sf "http://127.0.0.1:8080/ready" | head -c 500; echo

echo "========== ports =========="
ss -tlnp 2>/dev/null | grep -E '(:8080|:22)\s' || true

echo "========== logs (tail 100) =========="
docker compose -f docker-compose.yml logs --tail=100 newsroom

sleep 30
bash "${REPO_ROOT}/deploy/timeweb/scripts/go-live-verify.sh" || true

log "finished"
