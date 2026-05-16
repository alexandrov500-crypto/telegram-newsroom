#!/usr/bin/env bash
# Restore OUTPUT_DIR from a runtime_snapshot archive (inspection tree only).
# Usage: ./scripts/runtime_restore.sh var/backups/runtime_snapshots/runtime_ops_YYYYMMDD_HHMMSS
# For database restore use: python tools/backup_cli.py backup-restore <zip> --with-runtime

set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

if [[ $# -lt 1 ]]; then
  echo "usage: $0 <snapshot_directory> [OUTPUT_DIR=./runtime_ops_output]" >&2
  exit 2
fi

SNAPSHOT_DIR="$(cd "$1" && pwd)"
OUTPUT_DIR="${2:-${OUTPUT_DIR:-./runtime_ops_output}}"

if [[ ! -d "${SNAPSHOT_DIR}/runtime" ]]; then
  echo "error: ${SNAPSHOT_DIR}/runtime not found" >&2
  exit 2
fi

mkdir -p "${OUTPUT_DIR}"
rm -rf "${OUTPUT_DIR}/runtime"
cp -a "${SNAPSHOT_DIR}/runtime" "${OUTPUT_DIR}/runtime"

for sidecar in qualification.json runtime_bundle.zip ops_benchmark.json; do
  if [[ -f "${SNAPSHOT_DIR}/${sidecar}" ]]; then
    cp -a "${SNAPSHOT_DIR}/${sidecar}" "${OUTPUT_DIR}/${sidecar}"
  fi
done

echo "=== runtime restore (inspection tree) ==="
echo "restored: ${OUTPUT_DIR}/runtime"
echo "next: make runtime-index OUTPUT_DIR=${OUTPUT_DIR}"
echo "      make verify-runtime OUTPUT_DIR=${OUTPUT_DIR}"
echo "database: use backup_cli backup-restore for newsroom.db — see docs/RESTORE_PROCEDURE.md"
