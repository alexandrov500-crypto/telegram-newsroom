#!/usr/bin/env bash
# Run frozen inspection CLIs against OUTPUT_DIR (read-only).
# Usage: OUTPUT_DIR=./runtime_ops_output STRICT=1 ./scripts/runtime_sanity_check.sh

set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

OUTPUT_DIR="${OUTPUT_DIR:-./runtime_ops_output}"
STRICT="${STRICT:-0}"
PYTHON="${PYTHON:-python3}"

echo "=== runtime sanity check ==="
echo "OUTPUT_DIR=${OUTPUT_DIR}"
echo "STRICT=${STRICT}"
echo ""

if [[ ! -d "${OUTPUT_DIR}" ]]; then
  echo "error: OUTPUT_DIR does not exist: ${OUTPUT_DIR}" >&2
  exit 2
fi

required=(
  health_snapshot.json
  runtime_report.json
  runtime_manifest.json
  recovery_report.json
  compatibility_report.json
  qualification_history.json
  audit_snapshot.json
  runtime_capabilities.json
  capability_report.json
  runtime_policy.json
  policy_report.json
  runtime_index.json
)

echo "--- required artifacts (12 under runtime/) ---"
missing=0
for name in "${required[@]}"; do
  if [[ -f "${OUTPUT_DIR}/runtime/${name}" ]]; then
    echo "  ok  runtime/${name}"
  else
    echo "  MISSING  runtime/${name}"
    missing=$((missing + 1))
  fi
done

optional=(runtime_baseline.json drift_report.json)
echo ""
echo "--- optional artifacts ---"
for name in "${optional[@]}"; do
  if [[ -f "${OUTPUT_DIR}/runtime/${name}" ]]; then
    echo "  ok  runtime/${name}"
  else
    echo "  absent (optional)  runtime/${name}"
  fi
done

echo ""
echo "--- inspection CLIs ---"
run_cli() {
  local label="$1"
  shift
  echo ""
  echo ">> ${label}"
  if "$@"; then
    echo ">> exit 0"
  else
    local ec=$?
    echo ">> exit ${ec}"
    if [[ "${STRICT}" == "1" ]]; then
      return "${ec}"
    fi
  fi
}

if [[ "${STRICT}" == "1" ]]; then
  run_cli "runtime-index" "${PYTHON}" -m newsroom.cli runtime-index --path "${OUTPUT_DIR}" --strict
  run_cli "verify-runtime" "${PYTHON}" -m newsroom.cli verify-runtime --path "${OUTPUT_DIR}" --strict
  run_cli "validate-recovery" "${PYTHON}" -m newsroom.cli validate-recovery --path "${OUTPUT_DIR}" --strict
  run_cli "check-compatibility" "${PYTHON}" -m newsroom.cli check-compatibility --path "${OUTPUT_DIR}" --strict
else
  run_cli "runtime-index" "${PYTHON}" -m newsroom.cli runtime-index --path "${OUTPUT_DIR}"
  run_cli "verify-runtime" "${PYTHON}" -m newsroom.cli verify-runtime --path "${OUTPUT_DIR}"
  run_cli "validate-recovery" "${PYTHON}" -m newsroom.cli validate-recovery --path "${OUTPUT_DIR}"
  run_cli "check-compatibility" "${PYTHON}" -m newsroom.cli check-compatibility --path "${OUTPUT_DIR}"
fi

echo ""
if [[ "${missing}" -gt 0 ]]; then
  echo "sanity: FAIL (${missing} required file(s) missing)"
  echo "action: make runtime-nightly RUNTIME_DIR=./var/runtime OUTPUT_DIR=${OUTPUT_DIR}"
  exit 1
fi
echo "sanity: file checklist OK (review CLI statuses above)"
echo "docs: docs/BURN_IN_REPORT.md | drills: examples/failure_drills/"
