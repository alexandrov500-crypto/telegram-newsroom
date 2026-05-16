#!/usr/bin/env bash
# Local / CI mirror: bounded nightly runtime ops (repo root, bash).
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"
export PYTHONPATH="${ROOT}"
PYTHON="${PYTHON:-python3}"

set -a
# shellcheck source=/dev/null
source "${ROOT}/.github/ci-minimal.env"
set +a

RUN_ID="${CI_RUN_ID:-local}"
mkdir -p ci-artifacts/runtime-baseline ci-artifacts/runtime-live ci-artifacts/baseline-stage \
  "ci-artifacts/nightly-${RUN_ID}" "ci-artifacts/ops-${RUN_ID}"

for d in ci-artifacts/runtime-baseline ci-artifacts/runtime-live; do
  echo '{}' >"${d}/queue_pressure.json"
  echo '{"profile":"low","ci":true}' >"${d}/soak_report.json"
done

"${PYTHON}" tools/runtime_preflight.py --runtime-dir ci-artifacts/runtime-live --strict

"${PYTHON}" tools/runtime_ops.py bundle \
  --runtime-dir ci-artifacts/runtime-baseline \
  --output-dir ci-artifacts/baseline-stage
cp -f ci-artifacts/baseline-stage/runtime_bundle.zip ci-artifacts/baseline-stage/runtime_bundle_ci_baseline.zip

OUT="ci-artifacts/nightly-${RUN_ID}"
OPS="ci-artifacts/ops-${RUN_ID}"
"${PYTHON}" tools/runtime_ops.py nightly-check \
  --runtime-dir ci-artifacts/runtime-live \
  --output-dir "${OUT}" \
  --baseline ci-artifacts/baseline-stage/runtime_bundle_ci_baseline.zip \
  --short-soak \
  --strict \
  --json-output >"${OPS}/ops_summary.json"

for f in runtime_bundle.zip operational_dashboard.html qualification.json regression.json retention.json ops_benchmark.json; do
  if [[ -f "${OUT}/${f}" ]]; then cp -f "${OUT}/${f}" "${OPS}/${f}"; fi
done

echo "Artifacts staged under ${OPS}"
ls -la "${OPS}"
