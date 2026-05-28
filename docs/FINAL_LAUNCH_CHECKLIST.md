# Final Launch Checklist

## VPS launch steps

1. Pull latest code and dependencies on VPS.
2. Verify `.env` production values (`BOT_TOKEN`, `DATABASE_URL`, rollout flags).
3. Ensure single runtime process (`systemctl status newsroom` or compose health).
4. Run:
   - `make final-release-check`
   - `make final-public-check`
   - `make public-go-check`
5. Confirm Telegram operator checks:
   - `/release_status`
   - `/go_status`
   - `/continuity`
   - `/runtime_state`

## Final validation commands

```bash
make final-release-check
make final-public-check
make autonomous-weekly-report
make public-launch-playbook
```

## Rollback procedure

1. `/pause_autopublish`
2. Set `LIVE_ROLLBACK_MODE=true`
3. `make incident-report`
4. Fix root cause (runtime/Telegram/openai/dependency)
5. `/rollback_status` then `/resume_autopublish` only when blockers clear

## Emergency shutdown procedure

1. Set `GLOBAL_PUBLISH_PAUSE=true`
2. Stop service (`systemctl stop newsroom` or `docker compose stop newsroom`)
3. Preserve `var/runtime/*` diagnostics
4. Restore from backup if needed

## First 24h monitoring plan

- Watch every 30-60 min:
  - `/continuity`
  - `/last_alerts`
  - `/recent_failures`
- Keep `PREPUBLIC_QA_MODE=true` unless stage policy says otherwise.
- Escalate immediately on CRITICAL or repeated publish gate blocks.

## Operator response workflow

1. Detect alert (`/last_alerts`).
2. Check state (`/runtime_state`, `/go_status`).
3. Apply safe control (`/pause_autopublish` or rollback mode).
4. Run diagnostics (`make incident-report`).
5. Recover and verify (`make final-public-check`).
6. Resume only when `READY`/no critical blockers.
