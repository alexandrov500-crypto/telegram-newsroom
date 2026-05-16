# Multi-worker operational discipline

Requirements for T2 (Redis-backed multi-worker) within one node.

## Safe worker counts

| CPUs | Suggested max workers | Notes |
|------|----------------------|-------|
| 2 | 2 | Leave headroom for app + scheduler |
| 4 | 3–4 | Monitor queue lag |
| 8+ | ≤ cores | Diminishing returns past API limits |

Never exceed **CPU count** without profiling — context switching amplifies retry storms.

## Redis dependency expectations

- `REDIS_ENABLED=1` required for T2
- Redis must survive worker restarts; persistence policy operator-owned
- Reconnect churn: stabilize before scaling workers

## Strict lock requirements

- `PUBLISH_LOCK_STRICT=1` when more than one worker can publish
- Without strict mode: **fail-open risk** documented in v1.1 chaos validation

## Retry safety requirements

- `WORKER_RETRY_SAFE=1` before multi-worker retry-heavy workloads
- Prevents ack-before-enqueue loss on retry paths

## Operational monitoring expectations

- `python3 tools/scalability_diagnostics.py` on schedule
- Optional: `RUNTIME_DRIFT_MONITOR=1`, `SCHEDULER_DIAGNOSTICS=1`
- Queue depth via existing diagnostics / nightly artifacts

## Unsupported concurrency patterns

- Two nodes mounting same SQLite path (NFS/shared disk)
- Workers on different hosts without remote DB (T4)
- Publish without Redis lock in multi-worker mode
- Manual DB edits during worker processing

## Unsafe by design examples

```text
# UNSAFE: two workers, no strict lock
REDIS_ENABLED=1
WORKER_COUNT=2
PUBLISH_LOCK_STRICT=0

# UNSAFE: scale workers during retry storm
RUNTIME_RETRY_STORM_COUNT=40  # already saturated
WORKER_COUNT=8

# UNSAFE: shared SQLite over network filesystem
DATABASE_URL=sqlite:////nfs/share/newsroom.db
```

## Escalation guidance

1. Reduce to single worker
2. Enable strict flags
3. Clear retry storm root cause
4. If still saturated → architecture review (not more workers)

## Degradation expectations

- Redis down: queue stalls; strict publish may fail-closed
- Single worker fallback: supported emergency mode
- Do not claim HA — see T3/T4 docs
