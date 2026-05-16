#!/usr/bin/env bash
# Demo: release validation sequence (discipline, not deploy automation).
#
# Default: DRY-RUN for make/pytest execution.
# Run tests: DEMO_RUN=1 ./04_release_validation.sh

set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$ROOT"

OUTPUT_DIR="${OUTPUT_DIR:-./runtime_ops_output}"
DEMO_RUN="${DEMO_RUN:-0}"

# Deterministic echo order: header → ci-test → strict CLI gates → doc links.
run() {
  if [[ "$DEMO_RUN" == "1" ]]; then
    echo "+ $*"
    "$@"
  else
    echo "[dry-run] $*"
  fi
}

echo "=== 04 release validation ==="
echo ""

# Contract + smoke + runtime tests
run make ci-test

echo ""
echo "Runtime gate sequence (strict):"
run python3 -m newsroom.cli runtime-index --path "$OUTPUT_DIR" --strict
run python3 -m newsroom.cli verify-runtime --path "$OUTPUT_DIR" --strict
run python3 -m newsroom.cli validate-recovery --path "$OUTPUT_DIR" --strict
run python3 -m newsroom.cli check-compatibility --path "$OUTPUT_DIR" --strict
run python3 -m newsroom.cli inspect-policy --path "$OUTPUT_DIR" --strict

echo ""
echo "Checklist: docs/RELEASE_CHECKLIST.md"
echo "Process:  docs/RELEASE_PROCESS.md"
