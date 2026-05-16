#!/usr/bin/env bash
# Archive OUTPUT_DIR runtime artifacts (POSIX; no orchestration).
# Usage: OUTPUT_DIR=./runtime_ops_output ARCHIVE_DIR=./var/backups/runtime_snapshots ./scripts/runtime_snapshot.sh

set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

OUTPUT_DIR="${OUTPUT_DIR:-./runtime_ops_output}"
ARCHIVE_DIR="${ARCHIVE_DIR:-./var/backups/runtime_snapshots}"
TS="$(date -u +%Y%m%d_%H%M%S)"
DEST="${ARCHIVE_DIR}/runtime_ops_${TS}"

if [[ ! -d "${OUTPUT_DIR}/runtime" ]]; then
  echo "error: missing ${OUTPUT_DIR}/runtime — run make runtime-nightly first" >&2
  echo "hint: OUTPUT_DIR=${OUTPUT_DIR}" >&2
  exit 2
fi

mkdir -p "${ARCHIVE_DIR}"
mkdir -p "${DEST}"
cp -a "${OUTPUT_DIR}/runtime" "${DEST}/runtime"

for sidecar in qualification.json runtime_bundle.zip ops_benchmark.json; do
  if [[ -f "${OUTPUT_DIR}/${sidecar}" ]]; then
    cp -a "${OUTPUT_DIR}/${sidecar}" "${DEST}/${sidecar}"
  fi
done

cat >"${DEST}/SNAPSHOT.txt" <<EOF
created_utc=${TS}
source_output_dir=${OUTPUT_DIR}
note=Inspection artifact snapshot only — not a substitute for backup_cli DB backup
EOF

echo "=== runtime snapshot ==="
echo "archive: ${DEST}"
echo "next: scripts/runtime_sanity_check.sh OUTPUT_DIR=${OUTPUT_DIR}"
echo "      python tools/backup_cli.py backup-create  # database + RUNTIME_STATE_DIR"
