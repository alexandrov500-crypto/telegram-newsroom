# Worker runtime (production-lite)

This document describes the **async worker processes** (`python -m workers.ingest_worker`, `workers.ai_worker`, `workers.publisher_worker`) built on top of the internal job queue and **reliable transport** layer.

## Semantics

### At-least-once delivery

Jobs are delivered **at least once**:

- After a successful lease (`BRPOPLPUSH` to a processing list in Redis, or in-memory lease map), the worker must **ACK** (`LREM` + `DEL inflight:*`) or **NACK** (requeue / DLQ).
- If the worker crashes after lease but before ACK, the **inflight Redis key** TTL expires; a **recovery sweep** moves the job back to the pending list (or in-memory equivalent).

There is **no exactly-once** guarantee across crashes and retries without external idempotency (e.g. `publish_service` idempotency keys for publishes).

### Redis guarantees (current design)

- **Pending**: list `NEWSROOM_QUEUE_PREFIX:jobq:{ingest|ai|publisher}`
- **Processing**: list `...:jobq:{kind}:processing`
- **Lease marker**: `...:inflight:{delivery_id}` with TTL = visibility window
- **DLQ**: list `...:jobq:{kind}:dlq` (JSON record: `schema_version`, timestamps, `reason`, enriched metadata, full `original` envelope)

Recovery: any row in `processing` whose `inflight:{delivery_id}` key is **missing** (expired or never set) is treated as stale and **LPUSH**’d back to pending.

### In-memory limitations

The in-process transport keeps leases in RAM. **Process crash = possible loss** of in-flight jobs (no cross-process recovery). Suitable for development and single-node degraded mode.

## Typed dispatch

Handlers are registered by `JobType` (`INGEST_ARTICLE`, `PROCESS_CLUSTER`, …). The **dispatcher** reads `payload["job_type"]` and invokes the matching handler. This layer is **transport-agnostic**: it only sees `JobEnvelope`.

## Retries

- **Transient / rate-limited / external-service-failure**: exponential backoff with jitter, bounded by `WORKER_RETRY_DEADLINE_SEC` and attempt cap derived from settings.
- **Permanent** (`StructuredJobError` with `ErrorClass.PERMANENT` or classification): **no retry** — job goes to **DLQ**.
- **Poison** (retries exhausted or past deadline): **DLQ**.

## Graceful shutdown

- `SIGTERM` / `SIGINT` set an `asyncio.Event`.
- `lease_dequeue` uses **short** `BRPOP`/`BRPOPLPUSH` timeouts (default 1s) so the loop observes shutdown without hanging indefinitely.
- After stop, the runtime **waits** for in-flight tasks (bounded by `WORKER_GRACE_SHUTDOWN_SEC` sleep + `gather` on task set).

## Operational trade-offs

| Aspect | Choice | Trade-off |
|--------|--------|-----------|
| Orchestration | No Celery/Kafka | Simpler ops; you run more containers/processes yourself |
| Crash recovery | Visibility + inflight key | Extra Redis keys; rare duplicate execution on edge races |
| DLQ | Redis list / in-memory log | Manual replay not automated |
| Concurrency | `asyncio` semaphore per process | True CPU parallelism requires multiple processes |

## Future migration (optional)

If you later need Celery, Dramatiq, or a cloud queue:

1. Keep **dispatcher + `JobType` + handler implementations** as the stable contract.
2. Replace `worker/reliable_transport.py` with a broker adapter that still exposes `lease_dequeue` / `ack` / `nack_*` / `recover_stale`.
3. Keep **payload JSON** stable for replay tooling.

No code in this repo assumes Kubernetes or a service mesh.

## Further reading

- **`docs/RESILIENCE_AND_FAILURE_MODES.md`** — Redis outage behavior, DLQ operations, duplicate delivery, watchdog semantics, and operational runbooks.
