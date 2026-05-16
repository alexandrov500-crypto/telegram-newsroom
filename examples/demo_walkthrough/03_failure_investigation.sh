#!/usr/bin/env bash
# Demo: failure investigation sequence (inspection only, no auto-remediation).
#
# Default: DRY-RUN. Execute: DEMO_RUN=1 ./03_failure_investigation.sh

set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$ROOT"

OUTPUT_DIR="${OUTPUT_DIR:-./runtime_ops_output}"
DEMO_RUN="${DEMO_RUN:-0}"

# Deterministic echo order: header → investigation commands → playbook link.
run() {
  if [[ "$DEMO_RUN" == "1" ]]; then
    echo "+ $*"
    "$@"
  else
    echo "[dry-run] $*"
  fi
}

echo "=== 03 failure investigation ==="
echo "When index_status=FAIL or nightly exits non-zero:"
echo ""

# Catalog first — what is missing or misordered?
run make runtime-index OUTPUT_DIR="$OUTPUT_DIR"
run python3 -m newsroom.cli runtime-index --path "$OUTPUT_DIR" --json

# Incident narrative
run python3 -m newsroom.cli health --path "$OUTPUT_DIR" --report

# Integrity and portability
run make verify-runtime OUTPUT_DIR="$OUTPUT_DIR"
run make validate-recovery OUTPUT_DIR="$OUTPUT_DIR"
run make check-compatibility OUTPUT_DIR="$OUTPUT_DIR"

# Strict gate (WARNING also fails)
run python3 -m newsroom.cli runtime-index --path "$OUTPUT_DIR" --strict

echo ""
echo "Playbook: docs/examples/runtime_failure_investigation.md"
