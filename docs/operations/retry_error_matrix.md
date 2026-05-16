# Retry and error classification matrix

Operational reference for Telegram collector (Telethon), publisher (aiogram), workers, and Redis publish locks. Aligns with implementation in `collector/retry.py`, `publisher/retry.py`, and `publisher/publish_lock.py`.

## Policy summary

| Layer | Transient (retry) | Terminal (no retry) | Max attempts | Backoff |
|-------|-------------------|---------------------|--------------|---------|
| Telethon collector | `FloodWaitError`, `RPCError`, `OSError`, `TimeoutError`, `asyncio.TimeoutError` | `SessionPasswordNeededError`, other `Exception` | 4 (`max_attempts`) | FloodWait: `max(seconds, base×attempt)`; RPC: exp cap 30s |
| Publisher chunks | Any `BaseException` in `async_retry` | After attempts exhausted | 3 | Fixed 0.6s between attempts |
| Publish lock | Redis errors → fallback or strict deny | N/A (no API retry) | 1 acquire | TTL 180s (10–3600) |
| Worker job retry | Policy-driven re-enqueue | DLQ / ack per worker policy | Settings + envelope | Queue delay |

## Error classification table

| Error Type | Retry? | Backoff | Max Attempts | Escalation |
|------------|--------|---------|--------------|------------|
| `FloodWaitError` (Telethon) | Yes | `max(Telegram seconds, base_delay × attempt)` | 4 | If repeated in live validation: pause publishes; review cadence |
| `RPCError` transient (5xx-class) | Yes | Exponential, cap 30s | 4 | Log `telethon.op_recovered_after_retry`; metric `telegram_api_failures` on publish path |
| `OSError` / `TimeoutError` (network) | Yes | Exponential, cap 30s | 4 | Check network; session file lock if SQLite session |
| `SessionPasswordNeededError` | **No** | — | 1 | Recreate `TELETHON_SESSION_STRING`; 2FA not supported in MVP automation |
| Invalid / revoked auth key | **No** | — | 1 | Re-auth session; stop collector until session valid |
| Corrupted SQLite session file | **No** | — | 1 | Restore session backup or regenerate session |
| Publisher chunk send failure | Yes | 0.6s fixed | 3 | `mark_draft_failed`; operator retry from admin bot |
| Publish lock contention (`SET NX` false) | **No** | — | 1 | Return `ALREADY_HANDLED`; verify duplicate job |
| Publish lock strict + Redis down | **No** | — | 1 | `publish_lock_strict_denied`; fix Redis before multi-worker |
| Publish lock Redis error (non-strict) | Fallback once | — | 1 | Local lock; **do not** run multiple publishers |
| `FINALIZE_MISMATCH` (DB after send) | **No** auto-retry | — | 1 | Manual reconcile: channel has message, DB state wrong |
| Cadence block | **No** | — | 1 | Defer publish; review `cadence_blocked_publish` |
| OpenAI failures | Worker policy | Policy delay | Settings | DLQ / admin notify per runbooks |

## FloodWait handling policy

1. **Collector:** Sleep at least Telegram-requested seconds; never spin-tight loop.
2. **Publisher:** Proactive pacing via `ChannelPublishRateLimiter` (burst + min interval); FloodWait on aiogram is rare if pacing honored.
3. **Live validation:** Cap publishes (≤5 per session); stop if FloodWait repeats or `telethon_flood_waits` rises abnormally.
4. **Metrics:** `telethon_flood_waits` incremented on each collector FloodWait (see `collector/retry.py`).

## RPC retry policy

- Retries only inside `with_telethon_retries` wrapper.
- Non-RPC exceptions that are not in the transient tuple propagate immediately.
- After exhaustion, last exception is re-raised; caller must not assume partial collector state without idempotent design.

## Auth and session failure handling

| Symptom | Detection | Operator action |
|---------|-----------|-----------------|
| 2FA required | `SessionPasswordNeededError` in logs | Recreate session without interactive 2FA in automation path |
| Auth key invalid | Connect/auth errors, no recovery after reconnect | Regenerate session; verify API id/hash |
| SQLite session corrupt | Telethon session load errors | Replace session file from backup |
| Stale session after reset | High `telethon_reconnects` + API failures | Restart collector; re-auth once |

## Redis lock contention semantics

- **Acquired (`yield True`):** Holder must complete publish and release key in `finally` (delete).
- **Contended (`yield False`):** Treat as `ALREADY_HANDLED`; do not send duplicate Telegram messages.
- **TTL expiry:** Lock may expire mid-long-publish if TTL < publish duration; risk duplicate if second worker starts. Default TTL 180s; extend operationally only with documented tradeoff.
- **Strict mode:** No local fallback when Redis required; denies publish if Redis unavailable.

## Publish retry exhaustion behavior

1. Each HTML chunk: up to 3 `async_retry` attempts (`publisher/retry.py`).
2. On exhaustion: exception propagates → `publish_failures` / `telegram_api_failures` → draft `FAILED`.
3. **Partial chunks:** Earlier chunks may already be on channel; retry of full flow can duplicate unless lock + DB state prevent re-entry.
4. `publish_retries` metric increments on each publisher retry attempt (not on Telethon collector).

## Operator escalation guidance

| Severity | Condition | Action |
|----------|-----------|--------|
| LOW | Single transient retry, recovery log present | Monitor |
| MEDIUM | `telethon_reconnects` > 10 or `publish_lock_contention` elevated | Run `make live-telegram-diagnostics`; review session |
| HIGH | `retry_burst_window` ≥ storm threshold | Stop live validation; inspect worker queue |
| CRITICAL | `FINALIZE_MISMATCH` or duplicate channel posts | Halt auto-publish; manual DB/channel reconcile |

## Related documents

- [publish_idempotency.md](publish_idempotency.md)
- [../live_validation/live_validation_governance.md](../live_validation/live_validation_governance.md)
- [../runbooks/](../runbooks/)
