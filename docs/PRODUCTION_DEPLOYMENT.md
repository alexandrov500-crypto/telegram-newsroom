# Production deployment (VPS)

## VPS deployment checklist

1. Clone/sync repo to `/opt/newsroom` (or your path)
2. Python venv + `pip install -r requirements.txt`
3. Copy `.env` from `deploy/timeweb/.env.example` — **never commit secrets**
4. SQLite data dir writable: `data/`, `var/runtime/`
5. Install systemd unit:
   ```bash
   sudo cp deploy/systemd/newsroom.service /etc/systemd/system/
   # Edit User, WorkingDirectory, EnvironmentFile paths
   sudo systemctl daemon-reload
   sudo systemctl enable --now newsroom
   ```
6. Logrotate:
   ```bash
   sudo cp deploy/logrotate/newsroom /etc/logrotate.d/newsroom
   ```
7. Verify: `make ops-status`, `journalctl -u newsroom -f`
8. Burn-in ≥ 3 days: `make burnin-check`
9. Final gate: `make final-release-check` → `APPROVED`

## Controlled rollout

```bash
CONTROLLED_PUBLIC_ROLLOUT=true
ROLLOUT_STAGE=STAGE_0_PRIVATE_QA   # → STAGE_1 … STAGE_3_FULL_AUTONOMOUS
PREPUBLIC_QA_MODE=true             # recommended until STAGE_2
MODERATION_CHAT_ID=<private QA chat>
```

| Stage | Auto publish | Max pub/h |
|-------|--------------|-----------|
| STAGE_0_PRIVATE_QA | off | 2 |
| STAGE_1_LIMITED_PUBLIC | on (strict) | 4 |
| STAGE_2_OBSERVED_PUBLIC | on | 8 |
| STAGE_3_FULL_AUTONOMOUS | on | 24 |

Advance stage only after `make final-release-check` and `/go_status` are green.

## Restart safety

- **SIGTERM** triggers graceful shutdown (≤90s): scheduler stop, stale tick finalize, SQLite flush, event buffer flush
- On **boot**: stale pipeline ticks reconciled automatically (`pipeline.startup_stale_reconciled`)
- Runtime protection + rollout state restored from `var/runtime/*.json`

## Rollback

1. `/pause_autopublish` or `GLOBAL_PUBLISH_PAUSE=true`
2. `sudo systemctl stop newsroom`
3. Restore DB backup (`make backup-sqlite` / your restore script)
4. Deploy previous image/commit; `systemctl start newsroom`
5. `make incident-report` before/after for audit

## Docker (Timeweb)

See `deploy/timeweb/DEPLOY_WALKTHROUGH.md` and `deploy/systemd/newsroom-docker.service` for compose-on-boot.

## Operator tooling

```bash
make final-release-check
make release-readiness
make chaos-lite-validate
make autopublish-status
```

Telegram: `/release_status`, `/burnin_status`, `/go_status`, `/continuity`
