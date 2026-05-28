#!/usr/bin/env bash
# Interactive checklist — does not deploy automatically.
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

echo "=== VPS migration checklist ==="
echo ""
echo "[ ] 1. Mac: stop local runtime"
echo "       bash scripts/stop_local_newsroom.sh"
echo ""
echo "[ ] 2. Mac: stop VPS container if same BOT_TOKEN was on Mac"
echo "       ssh VPS 'docker stop telegram-newsroom'  # if needed"
echo ""
echo "[ ] 3. VPS: bootstrap host (once)"
echo "       bash deploy/vps/bootstrap.sh"
echo ""
echo "[ ] 4. VPS: clone repo, configure deploy/timeweb/.env"
echo "       cd deploy/timeweb && make up && make health"
echo ""
echo "[ ] 5. Mac: set NEWSROOM_RUNTIME_PROFILE=vps in .env"
echo "       Reload Cursor ( .cursorignore active )"
echo ""
echo "[ ] 6. Verify remote"
echo "       export VPS_HOST=... VPS_USER=ubuntu"
echo "       make server-status && make server-burnin"
echo ""
echo "[ ] 7. Mac: use dev-only"
echo "       bash scripts/dev_start.sh   # not start_mac_bot.sh"
echo ""

if pgrep -f "python.*-m app.main" >/dev/null 2>&1; then
  echo "WARNING: app.main still running on this Mac."
fi
if [[ -f .env ]] && grep -q "NEWSROOM_RUNTIME_PROFILE=vps" .env 2>/dev/null; then
  echo "OK: .env has NEWSROOM_RUNTIME_PROFILE=vps"
else
  echo "TIP: add NEWSROOM_RUNTIME_PROFILE=vps to .env after VPS is up"
fi
echo ""
echo "Docs: docs/PRE_PUBLIC_AUTONOMOUS_OPS.md"
