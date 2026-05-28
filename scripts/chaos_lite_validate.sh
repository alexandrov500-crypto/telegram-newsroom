#!/usr/bin/env bash
# Chaos-lite — delegates to tools/chaos_lite_validate.py (existing pytest patterns).
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "${ROOT}"
PYTHON="${PYTHON:-python3}"
exec "${PYTHON}" tools/chaos_lite_validate.py "$@"
