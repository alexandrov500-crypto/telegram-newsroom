# Consistency & integrity matrix

Component-level consistency models — production-lite, not distributed theory.

| Component | Consistency model | Failure mode | Recovery model |
|-----------|-------------------|--------------|----------------|
| **SQLite (newsroom DB)** | Single-writer; transactional per connection | Lock contention, corruption if multi-writer | Restore backup; WAL checkpoint; quiesce |
| **SQLite WAL file** | Durability with WAL; checkpoint coupling | Unbounded WAL growth | Quiesce + `wal_checkpoint` |
| **Redis queue** | At-least-once; visibility leases | Connection loss, memory pressure | Reconnect; stale reclaim; drain |
| **Redis publish lock** | Best-effort mutual exclusion per draft (TTL) | TTL expiry, partition | Wait TTL; strict deny; ops key delete |
| **Local publish lock** | Process-local mutex | Multi-process duplication | Redis + strict |
| **Evidence manifests** | Point-in-time catalog after nightly | Partial write, manual edit | Regenerate nightly |
| **Snapshots / OUTPUT_DIR** | Crash-consistent if copied quiesced | Disk full | Archive restore |
| **runtime_manifest checksums** | Deterministic over listed files | Missing files | Re-manifest |
| **Telegram delivery** | External at-least-once | Flood-wait, auth errors | Retry policies; operator tokens |
| **Retry queues (in-process)** | Coupled to transport | Storm, exhaustion | DLQ; safe retry flag |
| **Scheduler state** | In-process APScheduler | Overlap, crash mid-job | Restart; diagnostics |
| **Operator-maintained artifacts** | Human discipline | Stale history, wrong path | Docs + guardrails |
| **DLQ records** | Append-oriented list in Redis/memory | Flush | Replay index API |
| **Frozen JSON contracts** | Version 1 schema | Schema drift | ADR + major version only |

## Cross-cutting rules

1. **Source of truth for editorial state:** SQLite (single file).
2. **Source of truth for ops evidence:** `OUTPUT_DIR/runtime/*` after nightly.
3. **Redis is coordination, not authoritative archive.**
4. **Telegram is external; recovery does not rewind channel history.**
