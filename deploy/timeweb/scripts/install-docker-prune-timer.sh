#!/usr/bin/env bash
# Install systemd timer for regular Docker cache cleanup.
# Run on VPS as root: sudo bash deploy/timeweb/scripts/install-docker-prune-timer.sh
set -euo pipefail

REPO_ROOT="${REPO_ROOT:-/opt/newsroom}"
SYSTEMD_SRC="${REPO_ROOT}/deploy/systemd"

if [[ "${EUID}" -ne 0 ]]; then
  echo "Run as root (sudo) to install systemd units." >&2
  exit 1
fi

for unit in newsroom-docker-prune.service newsroom-docker-prune.timer; do
  src="${SYSTEMD_SRC}/${unit}"
  [[ -f "${src}" ]] || { echo "missing ${src}" >&2; exit 1; }
  install -m 0644 "${src}" "/etc/systemd/system/${unit}"
  echo "installed /etc/systemd/system/${unit}"
done

systemctl daemon-reload
systemctl enable --now newsroom-docker-prune.timer
systemctl status newsroom-docker-prune.timer --no-pager || true
echo "Next run:"
systemctl list-timers newsroom-docker-prune.timer --no-pager || true
