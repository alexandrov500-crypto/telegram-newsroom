# Publish idempotency and duplicate prevention

Review of `publisher/publish_service.py`, `publisher/publish_lock.py`, `publisher/telegram_publisher.py`, and DB state transitions.

## Pipeline overview

```
execute_admin_publication_flow
  → optional idempotency_key (Redis / in-memory)
  → publish_draft_lock (Redis SET NX or local asyncio.Lock)
  → approve + mark_draft_publishing
  → publish_draft_to_channel (chunked, per-chunk async_retry)
  → mark_draft_published
  → idempotency record on success
```

## Guaranteed behaviors

| Guarantee | Mechanism |
|-----------|-----------|
| Same process duplicate publish suppressed | `publish_draft_lock` local lock per `draft_id` |
| Concurrent workers same draft (Redis healthy) | Redis `SET NX` with TTL; second caller gets `ALREADY_HANDLED` |
| Duplicate job with same `idempotency_key` | Redis/memory store returns prior `message_id` |
| Draft already publishing/published | `approve_draft` / `mark_draft_publishing` returns `ALREADY_HANDLED` |
| Lock not acquired | No Telegram send; outcome `ALREADY_HANDLED` |
| Dry run | No Telegram API; outcome `DRY_RUN` |

## Non-guaranteed behaviors

| Gap | Risk | Mitigation |
|-----|------|------------|
| Lock TTL expires before publish completes | Second worker may acquire lock and send duplicate | Keep publishes short; tune TTL; single publisher T1 |
| Redis unavailable + non-strict lock | Per-process lock only | `PUBLISH_LOCK_STRICT=1` with `REDIS_ENABLED` for multi-worker |
| Partial chunk success then failure | Channel may have message 1..N-1; DB `FAILED` | Manual inspect channel; do not blind full retry |
| `FINALIZE_MISMATCH` | Message on channel; DB not `PUBLISHED` | Operator reconcile per runbook |
| Idempotency store loss (Redis flush) | Same key may publish again | 7-day TTL keys; accept rare duplicate on disaster |
| Retry after success (client double-click) | Usually blocked by lock + status | Use idempotency keys in worker jobs |
| Crash after send, before DB finalize | Orphan channel message | Timeline + `FINALIZE_MISMATCH` detection |

## Lock expiration edge cases

- Default TTL: **180 seconds** (`publish_draft_lock(..., ttl_sec=180)`).
- Key deleted in `finally` after successful publish path; early exit on contention never holds lock.
- If publish hangs > TTL, another worker can acquire → **duplicate risk**. Operational expectation: investigate hung publishes before TTL.
- `publish_lock_stale_suspected` metric (via `record_lock_event`) flags suspected stale lock scenarios in diagnostics buffer.

## Partial chunk persistence

- Chunks are sent sequentially; `sent_ids` accumulated in memory only.
- Failure on chunk *k* does not roll back Telegram messages 1..*k-1*.
- DB transitions to `FAILED` on `SEND_FAILED`; no automatic channel delete.

## Worker restart safety

- In-flight publish lost on process kill; lock may remain until TTL.
- Restarted worker: new job may see `ALREADY_HANDLED` (lock) or retry `FAILED` draft after `reset_failed_draft_to_pending` path in flow.
- `WORKER_RETRY_SAFE=1`: re-enqueue before ack on transient failures (see worker retry policy).

## Retry-after-success scenarios

| Scenario | Expected outcome |
|----------|------------------|
| Re-publish same draft id while `PUBLISHED` | `ALREADY_HANDLED` |
| Re-publish with same idempotency key | Prior `message_id` returned |
| Re-publish after `FAILED` | Flow may reset to pending and attempt again (new Telegram send) |
| Re-publish after partial chunk failure | **Manual** — channel may already have partial content |

## Known limitations

1. No distributed transaction between Telegram and SQLite.
2. Publisher `async_retry` retries all exception types (including `RuntimeError`).
3. `publish_retries` counts publisher-layer retries only.
4. Multi-chunk messages appear as multiple Telegram messages (by design).

## Operational expectations

- **T1 single-node:** local lock + DB status sufficient for most duplicate prevention.
- **T2 multi-worker:** require Redis + `PUBLISH_LOCK_STRICT=1`.
- **Live validation:** ≤5 publishes; verify channel after any `SEND_FAILED` or `FINALIZE_MISMATCH`.
- Run `make live-telegram-diagnostics` after incidents.

## Related documents

- [retry_error_matrix.md](retry_error_matrix.md)
- [../architecture/live_validation_runtime_flow.md](../architecture/live_validation_runtime_flow.md)
