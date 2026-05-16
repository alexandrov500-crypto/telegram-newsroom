# Recovery semantics specification

Honest, bounded recovery guarantees for operators.

## What recovery guarantees exist

1. **Inspection recovery** — Given a complete `OUTPUT_DIR` from nightly-check, `verify-runtime` and `validate-recovery` produce deterministic PASS/WARN/FAIL.
2. **Schema compatibility** — `check-compatibility` validates schema version 1 for present artifacts.
3. **Baseline drift** — With captured baseline, `compare-baseline` detects configured drift classes.
4. **Bundle replay** — `replay-runtime` extracts inspectable content when bundle present.
5. **Worker job recovery (Redis)** — Visibility timeout returns stale processing jobs to pending (transport-dependent).
6. **DLQ retention** — Terminal failures recorded with metadata for operator replay (`replay_dlq` where supported).
7. **Safe retry path** — With `WORKER_RETRY_SAFE=1`, retry re-enqueue precedes ack (reduces loss on crash).

## What recovery guarantees DO NOT exist

- Exactly-once job execution
- Automatic cross-node failover
- Zero-downtime SQLite file restore
- Telegram message undo after publish
- Self-healing without operator action
- Guaranteed RPO/RTO SLAs
- Recovery from silent manual DB edits
- Consistency between Redis flush and SQLite without reconciliation

## Ordering expectations

| Operation | Order |
|-----------|--------|
| Safe retry | enqueue → ack (same delivery) |
| Legacy retry | ack → enqueue |
| Successful job | handler complete → ack |
| Terminal failure | DLQ → finish (no retry) |
| Nightly inspection | frozen lifecycle 1..14 |
| File restore | quiesce → copy → validate |

## Replay expectations

- DLQ replay is **operator-initiated**; may duplicate side effects if handler not idempotent.
- `replay-runtime` is **read-only** inspection, not pipeline re-execution.
- Re-running nightly over same dir should be intentional (overwrite policy).

## Duplicate-delivery expectations

- Queue: **at-least-once** — handlers must tolerate duplicate delivery IDs where transport redelivers.
- Publish: lock reduces duplicate publish probability; not a proof of exactly-once.
- Telegram: API may retry; channel may receive duplicates if lock bypassed.

## Partial publish expectations

- Draft may be marked published in DB while Telegram fails → operator uses logs/DLQ.
- Lock contention → publish skipped (`ok=False`); not an error storm by design in strict paths.

## Rollback expectations

- Config rollback: revert `.env`; restart workers.
- Schema rollback: unsupported without restore from backup.
- Evidence rollback: restore prior `OUTPUT_DIR` tree from archive.

## Degraded recovery semantics

| Mode | Meaning |
|------|---------|
| T3 offline | Inspection from bundle only; no live publish |
| WARNING verify | Missing optional artifacts; required present |
| Strict lock deny | Publish refused — data safer than duplicate |
| WARN recovery | Missing optional bundle/benchmark — structure may be valid |

Degraded is **successful containment**, not full service.
