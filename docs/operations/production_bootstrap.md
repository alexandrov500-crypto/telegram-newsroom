# Production environment bootstrap

Ordered bootstrap for **production-lite** activation (single node, human-in-the-loop). Assumes staging sign-off grade **A** complete.

## Bootstrap order

| Step | Action | Verify |
|------|--------|--------|
| 1 | Provision host + persistent volumes (`/data` or `var/`) | disk writable |
| 2 | Copy `deploy/example.env.production-lite` → `.env` (host only) | `staging_environment_verify.py --strict` |
| 3 | Place Telethon session on volume | `TELETHON_SESSION_PATH` exists |
| 4 | Set `APP_DEPLOYMENT_PROFILE=production` | profile clamps burst/interval |
| 5 | `DRY_RUN=true` | no channel sends |
| 6 | Initialize SQLite (`DATABASE_URL`) | migrations if applicable |
| 7 | Redis (T2 only) | `redis-cli PING` |
| 8 | Run P0 diagnostics | see phases below |
| 9 | Start scheduler/worker (single) | logs clean |
| 10 | P1–P2 activation | [controlled_activation.md](../runbooks/controlled_activation.md) |

## Redis startup expectations

| Tier | `REDIS_ENABLED` | `PUBLISH_LOCK_STRICT` |
|------|-----------------|------------------------|
| T1 production-lite | `false` | `false` (local lock) |
| T2 multi-worker | `true` | `true` |

- Start Redis before workers when enabled.
- If Redis down in strict mode: publish **denied** (fail-closed).
- Never run multiple publishers with Redis down + non-strict fallback.

## SQLite and session handling

| Asset | Path | Notes |
|-------|------|-------|
| Newsroom DB | `DATABASE_URL` | single writer |
| Telethon session | `TELETHON_SESSION_PATH` or string | backup before upgrade |
| Runtime state | `RUNTIME_STATE_DIR` | cadence + timeline JSON |

- Do not share SQLite DB across hosts.
- Session file on same volume as backups (`NEWSROOM_BACKUP_DIR`).

## Diagnostics startup verification (P0)

```bash
make live-telegram-diagnostics
python3 tools/staging_environment_verify.py --strict
make governance-validate
```

Expected: diagnostics `status: OK` or WARNING without HIGH; verify `read_only: true`.

## DRY_RUN first boot policy

**Mandatory** for first production boot:

```env
DRY_RUN=true
NEWSROOM_SAFE_MODE=true   # optional extra caution
```

Run at least one pipeline tick + one admin publish attempt. Confirm log event `publish.dry_run_skipped`.

## Rollback-first startup strategy

Before enabling publish:

1. Tag deployment: `v3.1-production-lite`
2. Backup session + DB + `RUNTIME_STATE_DIR`
3. Document rollback command block in operator runbook
4. Keep `DRY_RUN=true` until P2 checklist signed

Instant rollback:

```env
DRY_RUN=true
```

Stop scheduler/worker processes — no further Telegram sends.

## Startup phases

### P0 — Diagnostics only

- Processes **stopped** or scheduler idle
- Run diagnostics + `make release-check` on host
- Capture baseline metrics JSON

### P1 — DRY_RUN validation

- Start single worker + scheduler
- Moderation flow without channel send
- Confirm cadence blocks logged when appropriate

### P2 — Bounded publish activation

- `DRY_RUN=false` with operator present
- ≤5 publishes first calendar day (operational policy)
- After each publish: `make live-telegram-diagnostics`

### P3 — Monitored steady-state

- Enter [72h_stability_window.md](72h_stability_window.md)
- No config churn; manual oversight

## Related documents

- [production_safeguards.md](production_safeguards.md)
- [controlled_activation.md](../runbooks/controlled_activation.md)
- [production_lite_rollout.md](production_lite_rollout.md)
