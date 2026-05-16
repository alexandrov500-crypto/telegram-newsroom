# Live staging sign-off

Controlled validation against real Telegram API on **staging channel only**. Governance cap: **≤5 publish operations** per sign-off session.

## Session metadata

| Field | Value |
|-------|-------|
| Date | 2026-05-16 |
| Tier | Staging |
| Branch | `v3-live-telegram-validation` |
| Operator | Automated pre-flight + maintainer completion |
| Channel | Staging test channel (redacted) |
| Max publishes allowed | 5 |

## Environment pre-flight

Command: `python3 tools/staging_environment_verify.py`

| Check | Result | Notes |
|-------|--------|-------|
| `.env` present on host | **PENDING** | No committed `.env` in repo (correct) |
| API id/hash | **PENDING** | Operator must set non-placeholder values |
| Telethon session | **PENDING** | Valid `TELETHON_SESSION_STRING` or file path |
| `TARGET_CHANNEL_ID` | **PENDING** | Must be staging channel, not production |
| `DRY_RUN` T0 | **PENDING** | Start with `true` |
| Redis | **N/A T1** | Disabled for single-worker T1 |
| Diagnostics v2 | **PASS** | `status: OK`, read-only, schema 2 |

## Live Telegram test execution

```bash
TELEGRAM_LIVE_VALIDATE=1 pytest tests/live -m live_telegram -v
```

| Run | Environment | Result | Evidence |
|-----|-------------|--------|----------|
| CI maintainer host (no `.env`) | `TELEGRAM_LIVE_VALIDATE=1` | **BLOCKED** | `ValueError: Not a valid string` — placeholder session |
| Expected staging | Valid `.env` + session | **PENDING** | Operator must re-run after checklist |

**Connect lifecycle (expected when credentials valid):**

- `build_telethon_client` → `ensure_connected` → `is_connected()` → `disconnect()`
- Reconnect metric increments on disconnect-before-connect path (bounded CI test proves metric wiring)

## Bounded CI proxy validation (executed)

| Area | Command | Result |
|------|---------|--------|
| Full bounded live suite | `make live-validation-validate` | **27 passed**, 1 deselected |
| Session recovery | `tests/live/recovery/` | **PASS** |
| FloodWait / pacing | `tests/live/floodwait/` | **PASS** |
| Publish integrity | `tests/live/publish_integrity/` | **PASS** |
| Failure injection proxy | `pytest tests/staging -q` | See failure_injection_results.md |

## Publish operations log (staging)

| # | draft_id | outcome | chunks | retries | duplicate? | Notes |
|---|----------|---------|--------|---------|------------|-------|
| — | — | — | — | — | — | **No live publishes executed** in automated sign-off (no credentials) |

Operator: append rows for up to 5 staging publishes during manual sign-off.

## Behavioral verification matrix

| Behavior | CI bounded | Staging live |
|----------|------------|--------------|
| Connect / disconnect | Mocked + optional live | **PENDING** live |
| Session reuse | SQLite path test | **PENDING** live |
| FloodWait handling | Mocked `telethon_flood_waits` | **PENDING** live |
| Retry exhaustion | RPC/auth tests | **PENDING** live |
| Lock contention | Redis mock | **PENDING** multi-worker |
| Diagnostics counters | **PASS** | **PASS** read-only |
| Reconnect semantics | **PASS** metric | **PENDING** live |

## Structured logs to capture (operator)

- `collector.telethon_reconnect`
- `telethon.op_recovered_after_retry`
- `publish.telegram_chunks_duration_sec`
- `publish.success` / `publish.channel_send_failed`
- `publish.idempotent_skip`
- `publisher.chunks_sent`

## Timing / metrics snapshot (pre-live)

From `make live-telegram-diagnostics` on 2026-05-16:

- `telethon_reconnects`: 0
- `telethon_flood_waits`: 0
- `publish_retries`: 0
- `publish_failures`: 0
- `publish_lock_contention`: 0
- `session_reset_suspected`: false

## Stop conditions triggered

None during automated pass.

## Sign-off status

| Gate | Status |
|------|--------|
| Bounded framework | **PASS** |
| Staging env verify tool | **PASS** (WARN expected without `.env`) |
| Live connect test | **PENDING** operator credentials |
| ≤5 staging publishes | **PENDING** operator |
| No duplicate delivery | **N/A** (no live publishes) |
| Readiness grade | **A−** framework + operator live completion → **A** |

## Maintainer completion checklist

- [ ] Copy `.env.example` → `.env` with staging secrets
- [ ] Confirm `TARGET_CHANNEL_ID` is staging-only
- [ ] `DRY_RUN=true` → pipeline smoke → `DRY_RUN=false` for ≤5 publishes
- [ ] Re-run `TELEGRAM_LIVE_VALIDATE=1 pytest tests/live -m live_telegram -v`
- [ ] Complete [operator_workflow_validation.md](../live_validation/operator_workflow_validation.md)
- [ ] Update publish table above
- [ ] Set readiness to **A** in `docs/v3_live_telegram_validation_report.md`
