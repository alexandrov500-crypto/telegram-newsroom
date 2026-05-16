# Controlled production activation runbook

Step-by-step activation after merge/tag `v3.1-production-lite`. **Single operator, single worker, human moderation.**

## Preconditions

- [ ] Staging sign-off grade **A**
- [ ] `python3 tools/staging_environment_verify.py --strict` → OK on prod host
- [ ] Backup: DB, session, `RUNTIME_STATE_DIR`
- [ ] Tag checked out: `v3.1-production-lite`

## Step 1 — Enable DRY_RUN

```env
DRY_RUN=true
APP_DEPLOYMENT_PROFILE=production
```

Restart processes. Confirm no Telegram channel posts.

## Step 2 — Verify diagnostics

```bash
make live-telegram-diagnostics
make governance-validate
```

| Check | Expected |
|-------|----------|
| `read_only` | true |
| `status` | OK or WARNING (no HIGH) |
| `session_reset_suspected` | false |

Save JSON snapshot to ops log.

## Step 3 — Enable publish (bounded)

```env
DRY_RUN=false
```

Keep:

```env
PUBLISH_CHANNEL_MIN_INTERVAL_SEC=300
PUBLISH_BURST_MAX_MESSAGES=5
PUBLISH_BURST_WINDOW_SEC=3600
```

**Do not** start second worker without Redis strict lock.

## Step 4 — First controlled post

1. Generate/approve draft via admin bot (human)
2. Publish once
3. Verify channel: single thread, expected chunks
4. Verify DB: draft `PUBLISHED`
5. Run diagnostics — note `publishes` / `drafts_published`

## Step 5 — Validate counters

| Metric | Expect after 1 publish |
|--------|------------------------|
| `publishes` or `drafts_published` | ≥1 |
| `publish_failures` | 0 |
| `publish_lock_contention` | 0–1 |
| `telethon_flood_waits` | 0 |

## Step 6 — Validate retry behavior

- Induce transient failure only in staging if needed
- In production: observe logs for `publish_chunk_* retry` — should be rare
- `publish_retries` should not spike >15/day

## Step 7 — Validate moderation flow

- [ ] Reject path works
- [ ] Approve denied when already published
- [ ] Cadence defer shows understandable message

## Step 8 — Shutdown / restart validation

1. `DRY_RUN=true` → publish → confirm skip
2. Stop worker gracefully
3. Restart worker
4. Retry-safe job: no duplicate (lock + status)

## Stop conditions

Stop activation and rollback if:

- Duplicate channel message
- `FINALIZE_MISMATCH`
- Diagnostics HIGH / `session_reset_suspected`
- FloodWait loop
- Operator abort

## Emergency rollback

```bash
# 1. Stop traffic
DRY_RUN=true   # in .env, restart services

# 2. Stop processes
# systemctl stop ... OR docker compose stop worker scheduler

# 3. Diagnostics
make live-telegram-diagnostics

# 4. Stuck drafts — runbook TELETHON / FAILED draft reset
```

Target recovery time: **< 5 minutes** to stop publishes.

## Operator checkpoints

| Checkpoint | When | Sign-off |
|------------|------|----------|
| C0 | After P0 diagnostics | ☐ |
| C1 | After DRY_RUN tick | ☐ |
| C2 | After 1st publish | ☐ |
| C3 | After restart test | ☐ |
| C4 | Enter 72h window | ☐ |

## Expected healthy metrics (T1 day 1)

| Metric | Range |
|--------|-------|
| `telethon_reconnects` | 0–3 |
| `publish_retries` | 0–5 |
| `publish_failures` | 0 |
| `telethon_flood_waits` | 0–2 |

## References

- [production_bootstrap.md](../operations/production_bootstrap.md)
- [72h_stability_window.md](../operations/72h_stability_window.md)
- [incident_response.md](incident_response.md)
