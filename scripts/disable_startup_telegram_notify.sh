#!/usr/bin/env bash
# Turn off Telegram «Newsroom started» banners in .env (local or VPS path).
set -euo pipefail
ENV_FILE="${1:-.env}"
if [[ ! -f "${ENV_FILE}" ]]; then
  echo "Missing ${ENV_FILE}" >&2
  exit 1
fi
if grep -q '^SEND_STARTUP_NOTIFICATION=' "${ENV_FILE}"; then
  sed -i.bak 's/^SEND_STARTUP_NOTIFICATION=.*/SEND_STARTUP_NOTIFICATION=false/' "${ENV_FILE}"
else
  echo 'SEND_STARTUP_NOTIFICATION=false' >> "${ENV_FILE}"
fi
echo "Set SEND_STARTUP_NOTIFICATION=false in ${ENV_FILE}"
