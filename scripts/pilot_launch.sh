#!/usr/bin/env bash
# First controlled Telegram pilot — steps 2–5 helper
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"
ENV_FILE="${ENV_FILE:-.env}"

red() { printf '\033[0;31m%s\033[0m\n' "$*"; }
grn() { printf '\033[0;32m%s\033[0m\n' "$*"; }
ylw() { printf '\033[0;33m%s\033[0m\n' "$*"; }

echo "=== STEP 1 hint: ops group ==="
ylw "Create private group → add @newsroom_ai_bot → post once → run:"
echo "  python3 scripts/list_telegram_channels.py --env-file $ENV_FILE"
echo ""

echo "=== STEP 2: strict preflight ==="
if ! python3 scripts/pilot_preflight.py --env-file "$ENV_FILE" --strict --send-test-message; then
  red "PILOT LAUNCH ABORTED — fix preflight first"
  exit 1
fi
grn "Preflight OK"
echo ""

echo "=== STEP 3: command simulation (done in preflight) ==="
ylw "In Telegram (after operator starts): /freeze_publishing /resume_live /live_status"
echo ""

read -r -p "Start operator node now? [y/N] " ans
if [[ "${ans,,}" != "y" && "${ans,,}" != "yes" ]]; then
  ylw "Stopped before STEP 4. Run manually: bash scripts/pilot_activate.sh"
  exit 0
fi

echo "=== STEP 4: activate ==="
ENV_FILE="$ENV_FILE" bash scripts/pilot_activate.sh
