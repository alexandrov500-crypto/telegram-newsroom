#!/usr/bin/env bash
# Install scheduled Docker cache cleanup (systemd timer if root, else user crontab).
set -euo pipefail

REPO_ROOT="${REPO_ROOT:-/opt/newsroom}"

install_systemd() {
  local SYSTEMD_SRC="${REPO_ROOT}/deploy/systemd"
  for unit in newsroom-docker-prune.service newsroom-docker-prune.timer; do
    src="${SYSTEMD_SRC}/${unit}"
    [[ -f "${src}" ]] || { echo "missing ${src}" >&2; return 1; }
    install -m 0644 "${src}" "/etc/systemd/system/${unit}"
    echo "installed /etc/systemd/system/${unit}"
  done
  systemctl daemon-reload
  systemctl enable --now newsroom-docker-prune.timer
  systemctl status newsroom-docker-prune.timer --no-pager || true
}

if [[ "${EUID}" -eq 0 ]]; then
  install_systemd
  exit 0
fi

if command -v sudo >/dev/null && sudo -n true 2>/dev/null; then
  sudo REPO_ROOT="${REPO_ROOT}" bash "$0"
  exit $?
fi

echo "no root — installing user crontab instead"
exec bash "${REPO_ROOT}/deploy/timeweb/scripts/install-docker-prune-cron.sh"
