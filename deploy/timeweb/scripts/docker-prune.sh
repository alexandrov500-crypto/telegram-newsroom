#!/usr/bin/env bash
# Safe scheduled Docker cache/image cleanup for VPS hosts.
# Never prunes volumes — only build cache, dangling/unused images, stopped containers.
set -euo pipefail

LOG_TAG="newsroom-docker-prune"
DISK_WARN_PCT="${DOCKER_PRUNE_DISK_WARN_PCT:-75}"
DISK_CRIT_PCT="${DOCKER_PRUNE_DISK_CRIT_PCT:-85}"
BUILDER_KEEP_HOURS="${DOCKER_PRUNE_BUILDER_KEEP_HOURS:-48}"
DRY_RUN="${DOCKER_PRUNE_DRY_RUN:-false}"

log() { echo "[${LOG_TAG}] $(date -u +%Y-%m-%dT%H:%M:%SZ) $*"; }

disk_use_pct() {
  df -P / | awk 'NR==2 {gsub(/%/,"",$5); print $5}'
}

df_line() {
  df -hP / | awk 'NR==2 {print $3 " used / " $2 " (" $5 ")"}'
}

docker_df_compact() {
  docker system df 2>/dev/null || true
}

run_cmd() {
  local desc="$1"
  shift
  if [[ "${DRY_RUN}" == "true" ]]; then
    log "DRY_RUN skip: ${desc}: $*"
    return 0
  fi
  log "start: ${desc}"
  if "$@" 2>&1 | while IFS= read -r line; do log "  ${line}"; done; then
    log "done: ${desc}"
  else
    log "warn: ${desc} exited non-zero"
  fi
}

main() {
  command -v docker >/dev/null || { log "docker not installed"; exit 1; }

  local before_pct after_pct
  before_pct="$(disk_use_pct)"
  log "disk before: $(df_line) usage=${before_pct}%"
  log "docker before:"
  docker_df_compact | while IFS= read -r line; do log "  ${line}"; done

  run_cmd "builder-prune-aged" docker builder prune -f --filter "until=${BUILDER_KEEP_HOURS}h"
  run_cmd "image-prune-dangling" docker image prune -f

  if [[ "${before_pct}" -ge "${DISK_WARN_PCT}" ]]; then
    log "disk >= ${DISK_WARN_PCT}% — aggressive builder + unused image prune"
    run_cmd "builder-prune-all" docker builder prune -af
    run_cmd "image-prune-unused" docker image prune -af
  fi

  if [[ "${before_pct}" -ge "${DISK_CRIT_PCT}" ]]; then
    log "disk >= ${DISK_CRIT_PCT}% — prune stopped containers (no volumes)"
    run_cmd "container-prune" docker container prune -f
    run_cmd "system-prune" docker system prune -f
  fi

  after_pct="$(disk_use_pct)"
  log "disk after: $(df_line) usage=${after_pct}% (was ${before_pct}%)"
  log "docker after:"
  docker_df_compact | while IFS= read -r line; do log "  ${line}"; done
}

main "$@"
