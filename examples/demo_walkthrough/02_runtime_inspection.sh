#!/usr/bin/env bash
# Demo: runtime inspection CLI sequence (deterministic order).
#
# Default: DRY-RUN. Execute: DEMO_RUN=1 ./02_runtime_inspection.sh
# Uses OUTPUT_DIR or shows examples/demo_outputs/ transcripts when dry-run.

set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$ROOT"

OUTPUT_DIR="${OUTPUT_DIR:-./runtime_ops_output}"
DEMO_RUN="${DEMO_RUN:-0}"

# Deterministic echo order: header → inspection commands → demo output hints.
run() {
  if [[ "$DEMO_RUN" == "1" ]]; then
    echo "+ $*"
    "$@"
  else
    echo "[dry-run] $*"
  fi
}

echo "=== 02 runtime inspection (v1.0.0) ==="
echo "OUTPUT_DIR=$OUTPUT_DIR"
echo ""

# Fixed inspection order for demos and operator habit.
run make runtime-index OUTPUT_DIR="$OUTPUT_DIR"
run make runtime-health OUTPUT_DIR="$OUTPUT_DIR"
run make runtime-report OUTPUT_DIR="$OUTPUT_DIR"
run make verify-runtime OUTPUT_DIR="$OUTPUT_DIR"
run make check-compatibility OUTPUT_DIR="$OUTPUT_DIR"
run make inspect-policy OUTPUT_DIR="$OUTPUT_DIR"

if [[ "$DEMO_RUN" != "1" ]]; then
  echo ""
  echo "Example transcripts (sanitized):"
  for f in runtime-index verify-runtime audit-runtime compare-baseline; do
    echo "  examples/demo_outputs/${f}.txt"
  done
fi
