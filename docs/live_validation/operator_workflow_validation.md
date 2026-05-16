# Operator workflow validation (live)

Manual checklist for real Telegram operations — complements automated bounded tests.

## Moderation fatigue

| Check | Pass criteria |
|-------|---------------|
| Approve/reject flows clear | Status visible in admin bot |
| Long sessions | No unexplained bot freeze > 5 min |
| Error messages | Actionable without reading traceback |

**Pain point log:** note vague errors, missing draft IDs, unclear next step.

## DLQ ergonomics

| Check | Pass criteria |
|-------|---------------|
| DLQ visible | `/ops/dlq` or documented path works |
| Replay understood | Operator knows replay is manual |
| Terminal vs retry | DLQ meta explains classification |

## Recovery clarity

| Check | Pass criteria |
|-------|---------------|
| Stuck `publishing` | Runbook step to reset draft |
| Redis down | T1 fallback documented |
| Strict lock deny | Message explains fail-closed |

## Retry visibility

| Check | Pass criteria |
|-------|---------------|
| Worker logs | `worker.job_retry` with attempt count |
| Storm warning | Watchdog / diagnostics surface burst |
| Safe mode | `WORKER_RETRY_SAFE=1` documented |

## Publish visibility

| Check | Pass criteria |
|-------|---------------|
| Chunk count logged | `publisher.chunks_sent` |
| Partial failure | Draft marked failed; channel state inspectable |
| Cadence defer | `cadence_blocked_publish` understandable |

## Operational discoverability

| Check | Pass criteria |
|-------|---------------|
| START_HERE | Links live validation docs |
| `make ops-summary` | Health + risk indicators |
| `live_telegram_diagnostics.py` | JSON readable |

## Confusing flows (document findings)

Record in validation report:

- Steps requiring tribal knowledge
- CLI vs bot duplication
- Flags that must be set together (Redis + strict lock)

## Manual recovery friction

| Scenario | Friction score (1–5) | Notes |
|----------|----------------------|-------|
| Republish after fail | | |
| Session re-auth | | |
| OUTPUT_DIR inspect | | |

## Sign-off

Operator name, date, channel used (redacted), validation tier (staging / 24h).
