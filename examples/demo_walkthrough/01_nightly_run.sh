#!/usr/bin/env bash
# Demo: nightly runtime ops sequence (shell-first, not orchestration).
#
# Default: DRY-RUN (prints commands only).
# Execute for real:  DEMO_RUN=1 ./01_nightly_run.sh
#
# Requires: repo root, make install-dev already done for real runs.

set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$ROOT"

RUNTIME_DIR="${RUNTIME_DIR:-./var/runtime}"
OUTPUT_DIR="${OUTPUT_DIR:-./runtime_ops_output}"
DEMO_RUN="${DEMO_RUN:-0}"

# Deterministic echo order: header → config → commands → footer.
run() {
  if [[ "$DEMO_RUN" == "1" ]]; then
    echo "+ $*"
    "$@"
  else
    echo "[dry-run] $*"
  fi
}

echo "=== 01 nightly run ==="
echo "ROOT=$ROOT"
echo "RUNTIME_DIR=$RUNTIME_DIR"
echo "OUTPUT_DIR=$OUTPUT_DIR"
echo "DEMO_RUN=$DEMO_RUN (set DEMO_RUN=1 to execute)"
echo ""

# Sequential nightly-check — same order as tools/runtime_ops.py (no DAG).
run make runtime-preflight RUNTIME_DIR="$RUNTIME_DIR"
run make runtime-nightly RUNTIME_DIR="$RUNTIME_DIR" OUTPUT_DIR="$OUTPUT_DIR"

echo ""
echo "Artifacts expected under: $OUTPUT_DIR/runtime/"
echo "Last written: runtime_index.json"
echo "Sample JSON (no live run): examples/runtime_samples/"
