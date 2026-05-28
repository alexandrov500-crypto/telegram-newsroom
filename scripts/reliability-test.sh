#!/usr/bin/env bash
# Phase 3 reliability + chaos-lite test runner.
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "${ROOT}"
PYTHON="${PYTHON:-python3}"

echo "==> Invariant + reliability tests"
"${PYTHON}" -m pytest tests/reliability tests/test_reliability_phase2.py tests/test_execution_node_role.py \
  tests/test_startup_validation_extended.py tests/test_draft_status_flow.py \
  -q --tb=short "$@"

echo "==> Canonical metrics audit (informational)"
"${PYTHON}" - <<'PY'
from observability.canonical_metrics import audit_exported_metrics
from utils.metrics import export_snapshot

audit = audit_exported_metrics(export_snapshot())
if any(audit.values()):
    print("non-canonical metrics (review METRICS_CANONICAL.md):", audit)
else:
    print("metrics within canonical set (or empty export)")
PY

echo "OK reliability-test"
