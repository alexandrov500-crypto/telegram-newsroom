# Operational invariants registry

Explicit production-lite guarantees. **Not formal proofs** — operator-verifiable semantics.

## Queue delivery (Redis transport)

| Field | Value |
|-------|--------|
| **Invariant** | At-least-once delivery while Redis and workers healthy; visibility timeout enables stale reclaim |
| **Violation symptoms** | Jobs vanish after crash; duplicate processing without idempotency |
| **Detection** | Queue depth diagnostics; `recoverable_processing_estimate`; worker logs |
| **Recovery** | Stale job reclaim; DLQ replay; fix Redis |
| **Unsupported** | Exactly-once without app idempotency; cross-region queue |

## Retry semantics

| Field | Value |
|-------|--------|
| **Invariant (default)** | Bounded retries per policy; terminal → DLQ |
| **Invariant (`WORKER_RETRY_SAFE=1`)** | Re-enqueue **before** ack on retry path |
| **Invariant (legacy)** | Ack then enqueue — crash window may lose retry |
| **Violation symptoms** | Retry storm; DLQ flood; missing retry after worker death |
| **Detection** | `retry_burst_window`; reliability diagnostics traces |
| **Recovery** | Fix root cause; enable safe mode; reduce workers |
| **Unsupported** | Infinite retry; retry without DLQ cap |

## Publish lock

| Field | Value |
|-------|--------|
| **Invariant (strict + Redis)** | At most one publisher holds lock per `draft_id` (SET NX EX) |
| **Invariant (strict, Redis down)** | Publish denied (fail-closed) |
| **Invariant (legacy local)** | Per-process `asyncio.Lock` only |
| **Violation symptoms** | Duplicate channel posts; lock contention metrics |
| **Detection** | `publish_lock_*` counters; lock event snapshot |
| **Recovery** | Enable strict + stable Redis; single worker fallback |
| **Unsupported** | Cross-node lock without Redis |

## Snapshot / inspection consistency

| Field | Value |
|-------|--------|
| **Invariant** | Nightly pipeline produces 12 required `runtime/*.json` under `OUTPUT_DIR` per frozen order |
| **Violation symptoms** | `verify-runtime` FAIL; missing manifest entries |
| **Detection** | `make verify-runtime`; `runtime_sanity_check.sh` |
| **Recovery** | Re-run `runtime-nightly`; compare-baseline |
| **Unsupported** | Partial nightly treated as complete without WARNING |

## Recovery ordering

| Field | Value |
|-------|--------|
| **Invariant** | Restore drills: quiesce writers → file copy → validate-recovery |
| **Violation symptoms** | DB corruption; checksum mismatch |
| **Detection** | `validate-recovery`; recovery_report status |
| **Recovery** | Roll back to prior bundle; quiesce and retry |
| **Unsupported** | Live restore over active SQLite |

## Evidence integrity

| Field | Value |
|-------|--------|
| **Invariant** | Manifest lists artifacts; schema version 1 compatible |
| **Violation symptoms** | compatibility_report FAIL; drift vs baseline |
| **Detection** | `check-compatibility`; `compare-baseline` |
| **Recovery** | Regenerate nightly; restore from archive |
| **Unsupported** | Manual edit of frozen artifacts without ADR |

## WAL maintenance

| Field | Value |
|-------|--------|
| **Invariant** | Single writer to SQLite file; WAL checkpoint during quiesce |
| **Violation symptoms** | Large `-wal` file; slow writes |
| **Detection** | drift monitor `wal_bytes`; scalability diagnostics |
| **Recovery** | Stop workers → `PRAGMA wal_checkpoint(TRUNCATE)` |
| **Unsupported** | Multi-writer SQLite; NFS database path |

## Scheduler overlap

| Field | Value |
|-------|--------|
| **Invariant** | With `SCHEDULER_DIAGNOSTICS=1`, overlapping same-job runs are recorded |
| **Violation symptoms** | Missed intervals; stacked pipeline jobs |
| **Detection** | scheduler diagnostics snapshot; overlap counter |
| **Recovery** | Widen interval; reduce load |
| **Unsupported** | Distributed scheduler in-repo |

## Bounded memory / traces

| Field | Value |
|-------|--------|
| **Invariant** | Reliability diagnostic rings capped (e.g. 256 traces) |
| **Violation symptoms** | RSS growth without retention |
| **Detection** | soak/resource stability; drift monitor |
| **Recovery** | Restart process; retention pass |
| **Unsupported** | Unbounded in-process history for months without restart |
