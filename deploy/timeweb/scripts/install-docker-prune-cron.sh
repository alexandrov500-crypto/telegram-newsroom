#!/usr/bin/env bash
# Install user crontab entry for Docker cache cleanup (no root required).
set -euo pipefail

REPO_ROOT="${REPO_ROOT:-/opt/newsroom}"
SCRIPT="${REPO_ROOT}/deploy/timeweb/scripts/docker-prune.sh"
LOG_FILE="${REPO_ROOT}/logs/docker-prune.log"
MARKER="# newsroom-docker-prune"

[[ -x "${SCRIPT}" ]] || chmod +x "${SCRIPT}"
mkdir -p "$(dirname "${LOG_FILE}")"

CRON_LINE="30 4 * * * flock -n /tmp/newsroom-docker-prune.lock ${SCRIPT} >> ${LOG_FILE} 2>&1 ${MARKER}"

tmp="$(mktemp)"
crontab -l 2>/dev/null | grep -v "${MARKER}" > "${tmp}" || true
echo "${CRON_LINE}" >> "${tmp}"
crontab "${tmp}"
rm -f "${tmp}"

echo "installed crontab:"
crontab -l | grep "${MARKER}" || true
