#!/usr/bin/env bash
# Quick static check before push/deploy (run from repo root or deploy/timeweb).
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/../../.." && pwd)"
TW="${ROOT}/deploy/timeweb"

fail() { echo "FAIL: $*" >&2; exit 1; }
ok() { echo "OK: $*"; }

test -f "${TW}/Dockerfile" || fail "missing Dockerfile"
test -f "${TW}/docker-compose.yml" || fail "missing docker-compose.yml"
test -f "${TW}/Makefile" || fail "missing Makefile"
test -f "${TW}/.env.example" || fail "missing .env.example"
test -f "${ROOT}/docker/http_ready_probe.py" || fail "missing http_ready_probe.py"
test -f "${ROOT}/docker/healthcheck.py" || fail "missing healthcheck.py"
test -f "${ROOT}/requirements.txt" || fail "missing requirements.txt"

grep -q 'context: ../..' "${TW}/docker-compose.yml" || fail "compose build context should be ../.."
grep -q 'dockerfile: deploy/timeweb/Dockerfile' "${TW}/docker-compose.yml" || fail "dockerfile path"
grep -q '/opt/newsroom/data' "${TW}/docker-compose.yml" || fail "bind mount data path"
grep -q 'stop_grace_period: 45s' "${TW}/docker-compose.yml" || fail "stop_grace_period"
grep -q 'http_ready_probe.py' "${TW}/docker-compose.yml" || fail "healthcheck probe"
grep -q 'STOPSIGNAL SIGTERM' "${TW}/Dockerfile" || fail "STOPSIGNAL in Dockerfile"
grep -q 'tini' "${TW}/Dockerfile" || fail "tini in Dockerfile"

ok "production files and paths look consistent"
echo "Next: cp deploy/timeweb/.env.example deploy/timeweb/.env (on VPS only)"
