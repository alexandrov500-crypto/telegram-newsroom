#!/usr/bin/env bash
# Local release gate: tests + preflight + nightly + release_qualification (strict).
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"
export PYTHONPATH="${ROOT}"
PYTHON="${PYTHON:-python3}"

"${PYTHON}" -m pytest tests/runtime tests/smoke -q --tb=short --maxfail=1

bash "${ROOT}/scripts/nightly_runtime.sh"

RUN_ID="${CI_RUN_ID:-local}"
OUT="ci-artifacts/nightly-${RUN_ID}"
OPS="ci-artifacts/ops-${RUN_ID}"
REL="ci-artifacts/ops-release-${RUN_ID}"
mkdir -p "${REL}"

set -a
# shellcheck source=/dev/null
source "${ROOT}/.github/ci-minimal.env"
set +a

"${PYTHON}" tools/release_qualification.py \
  --runtime-bundle "${OUT}/runtime_bundle.zip" \
  --baseline ci-artifacts/baseline-stage/runtime_bundle_ci_baseline.zip \
  --strict \
  --require-regression-ok \
  --json-output "${REL}/qualification_gate.json" \
  --output-report "${REL}/qualification_gate.txt"

for f in runtime_bundle.zip operational_dashboard.html qualification.json regression.json retention.json ops_benchmark.json ops_summary.json; do
  if [[ -f "${OPS}/${f}" ]]; then cp -f "${OPS}/${f}" "${REL}/${f}"; fi
done

echo "Release-check artifacts under ${REL}"
ls -la "${REL}"
