# Resilience and failure modes

This document describes runtime guarantees for the **production-lite** worker stack: optional Redis + reliable lists, in-process SQLite/PostgreSQL, and the async `WorkerRuntime`. It is aimed at operators and maintainers who need predictable recovery without adopting a separate broker framework.

## At-least-once delivery

Jobs are dequeued with a **visibility lease** (Redis inflight key with TTL, or in-memory deadline). If a worker crashes or stalls past the lease, the job becomes visible again after `recover_stale` / TTL expiry.

**Guarantee:** each logical job is **processed at least once** if the transport and workers eventually run.

**Trade-off:** the same job may be delivered **more than once** (e.g. after a crash between handler success and `ack`, or duplicate recovery). Handlers must be **idempotent** where duplicates would cause user-visible harm (especially publication — see publish idempotency keys in `publisher/publish_service.py`).

## Duplicate delivery risks

| Scenario | Effect |
|----------|--------|
| Worker dies after side effects but before `ack` | Job retries; duplicate side effects possible |
| Inflight TTL too short vs handler duration | Job requeued while still running; parallel duplicates |
| Redis `SETEX` for inflight fails transiently | Rare edge; lease may be missing until retry path |

Mitigations already in code: bounded `worker_max_job_sec`, visibility `worker_visibility_sec`, handler error classification, DLQ for terminal failures, **publish idempotency** + **publish lock** for multi-worker sends.

## Recovery guarantees

- **Startup:** each `WorkerRuntime` calls `recover_stale` once before the main loop to requeue processing items whose inflight marker expired.
- **Redis unavailable:** transport operations use **bounded retries** with exponential backoff + jitter (`redis_transport_*` settings). The dequeue loop **does not exit** on transient errors; it degrades into longer sleeps (`monotonic_backoff_sleep_sec`).
- **Reconnect:** use `reconnect_redis(settings)` (admin/ops) or process restart; singleton client is re-created on `init_redis_from_settings` after `close_redis`.

## Degraded Redis behavior

When Redis is misconfigured or down at process start, `redis_enabled=true` may leave the app without a client (degraded). Worker bootstrap uses **in-memory reliable transport** if Redis is disabled or unavailable: same API, **no cross-process** queueing.

During runtime, repeated Redis errors surface as **warning logs** (`reliable_transport.brpoplpush_degraded`, `redis.transport_retry`, `redis.transport_recovered`). No automatic process stop is performed.

## DLQ (dead-letter queue) semantics

Terminal failures and retry exhaustion call `nack_dlq`, which stores a JSON record (schema `schema_version`):

- `dead_lettered_at`, `kind`, `delivery_id`, `reason`, `original` job JSON
- Enriched metadata from the runtime: `failure_class`, `attempt`, `job_type`, `handler_traceback`, `terminal` (`permanent` | `retries_exhausted`), policy flags when applicable

**Admin CLI:** `dlq-list`, `dlq-inspect`, `dlq-replay` (replay removes the entry and re-enqueues the `original` envelope).

## Queue pressure and watchdogs

Heartbeat iterations (default every ~5s in the worker loop) attach:

- **Queue pressure:** pending/processing depth, estimated oldest pending age (`_enqueue_wall_ts` on tail of pending list in Redis), sampled inflight ages from Redis TTL.
- **Saturation warnings:** `worker.queue_pressure` events when thresholds in `runtime_*` settings are exceeded.
- **Watchdogs (warnings only):** `worker.runtime_watchdog` for long-running active jobs, retry bursts, stale success under load, possible starvation (pending>0, processing=0). **No SIGKILL or forced shutdown** is issued from this layer.

## Publication pipeline

`execute_admin_publication_flow` uses:

1. Optional **idempotency key** → skip duplicate Telegram sends if a prior success was recorded.
2. **Redis publish lock** (or local asyncio lock) per `draft_id` to reduce concurrent double-publish across workers.
3. DB state transitions (`mark_draft_publishing` / `mark_draft_published`) to detect already-handled paths.

Telegram duplicate posts are still possible if idempotency keys are omitted and two workers bypass DB checks due to races; recommended: always pass stable idempotency keys from worker jobs.

## SQLite / in-memory development mode

With `redis_enabled=false`, the reliable transport is **in-process only**. Limitations:

- No cross-process queue; second worker process does not share the queue.
- Crash during processing can **lose** in-flight jobs (no durable inflight).
- DLQ and pending queues reset on process exit.

Use Redis-backed transport for multi-worker or durable queue semantics.

## Operational recovery procedures

1. **Stuck pending growth:** inspect `worker-queue-snapshot` and `queue-pressure` CLI; scale workers or fix slow handlers; tune `worker_max_concurrency` / visibility.
2. **DLQ growth:** `dlq-inspect` a sample; fix root cause; `dlq-replay` after code/config fix if safe.
3. **Redis outage:** workers keep retrying; restore Redis; optional rolling restart after long outage to clear odd half-open states.
4. **Poison messages:** already in DLQ; do not replay until the payload is safe to re-run.

## Recommended production settings (starting point)

- `WORKER_VISIBILITY_SEC` comfortably above p99 handler duration (but below “acceptable redelivery delay”).
- `WORKER_MAX_JOB_SEC` below visibility to allow lease renewal via completion or intentional nack paths.
- `REDIS_TRANSPORT_MAX_RETRIES` / backoff caps aligned with your SLO for transient blips.
- Tune `RUNTIME_QUEUE_PENDING_WARN`, `RUNTIME_RETRY_STORM_COUNT`, etc. to your traffic so logs stay actionable.

## Known limitations

- Queue lag and inflight ages are **samples/estimates**, not exact accounting.
- Watchdogs use in-process counters; separate CLI processes do not see live worker state except via Redis/DB.
- DLQ replay is **operator responsibility**; replays are still at-least-once.
