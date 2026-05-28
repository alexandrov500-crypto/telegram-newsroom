# Technical debt freeze audit

## Safe to leave

| Item | Rationale |
|------|-----------|
| JSONL publish journal (not SQL) | Simple, append-only audit |
| Dual bot trees (`app/` vs `bot/`) | Isolated; newsroom runtime uses `app/` |
| File-based `operational_mode.json` | Explicit, reloadable |
| Optional Redis queue | Off by default on Mac/VPS lite |

## Refactor later (non-blocking)

| Item | Risk if touched now |
|------|---------------------|
| Merge `utils/error_classifier` with worker retry taxonomy | Low priority |
| Single HTML ops dashboard framework | Cosmetic |
| `pipeline_ticks` retention cron | Ops load only |

## Dangerous debt (do not expand)

| Item | Action |
|------|--------|
| Multiple publish entrypoints | Keep `publish_service.execute_admin_publication_flow` canonical |
| `FIRST_POST_DEBUG` on production | Blocked in startup validation |
| Second poller without role env | Blocked INV-001 |

## Delete candidates (mark deprecated first)

| Path | Status |
|------|--------|
| `TELEGRAM_STARTUP_NOTIFY` alias | Deprecated → use `SEND_STARTUP_NOTIFICATION` |
| Duplicate `canary_status` bot commands | See `bot/ops_consolidation` |
| Unused `REPLAY_MODE` in production `.env` | Document only |

## Entropy rule

No new feature flags without `docs/PUBLIC_INTERFACES.md` update and expiry date.
