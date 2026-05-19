#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$ROOT"

echo "[staging] bootstrap directories"
mkdir -p var/runtime var/backups var/log var/reports var/incidents

if [[ -f deploy/bootstrap.sh ]]; then
  bash deploy/bootstrap.sh
fi

echo "[staging] python validation suite"
python3 -m bot.operations.cli validate-staging "$@"

echo "[staging] validate-staging complete"
