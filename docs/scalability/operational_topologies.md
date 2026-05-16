# Operational topology classification (v1.8)

Supported vs experimental deployment shapes for the production-lite newsroom platform.

## Summary

| ID | Name | Supported | Primary use |
|----|------|-----------|-------------|
| T0 | Single-process local | Yes | Dev, demos, contract tests |
| T1 | Single-node production-lite | Yes | Default production-lite |
| T2 | Multi-worker Redis-backed | Yes (with flags) | Throughput within one node |
| T3 | Degraded / offline recovery | Yes (bounded) | DR, inspection-only, restore drills |
| T4 | Unsupported experimental scaling | No | Lab only; no operational guarantees |

---

## T0 — single-process local

**Supported workload:** Low volume; manual runs; CI; `make runtime-nightly` on laptop.

**Operational assumptions:** SQLite file local; Redis optional; no HA; single writer to DB.

**Failure domains:** Process crash loses in-memory state only; queue may be in-memory or Redis depending on config.

**Recovery expectations:** Restart process; replay from SQLite + optional Redis pending if enabled.

**Scaling ceiling:** ~1 concurrent publish pipeline; bounded by single event loop and API rate limits.

**Known unsafe paths:** Treating T0 load tests as production capacity proof; multi-worker without Redis.

---

## T1 — single-node production-lite

**Supported workload:** Daily newsroom operations; nightly inspection; single worker or co-located app+worker.

**Operational assumptions:** One host; one SQLite DB; `OUTPUT_DIR` on local disk; Telegram/OpenAI quotas dominate.

**Failure domains:** Host disk, SQLite corruption (rare), token expiry, upstream API outages.

**Recovery expectations:** Restore from snapshot bundle; `validate-recovery`; optional Redis re-queue if enabled.

**Scaling ceiling:** One DB writer; recommend ≤2 workers unless T2 discipline applied.

**Known unsafe paths:** Unbounded `OUTPUT_DIR` growth; skipping WAL maintenance; running scheduler + heavy workers on overloaded CPU without diagnostics.

---

## T2 — multi-worker Redis-backed

**Supported workload:** Parallel job processing on one node with Redis transport and strict publish lock.

**Operational assumptions:** `REDIS_ENABLED=1`; `WORKER_RETRY_SAFE=1`; `PUBLISH_LOCK_STRICT=1` for publish safety; shared SQLite still **one writer**.

**Failure domains:** Redis partition, lock contention, retry storms, WAL growth under concurrent readers.

**Recovery expectations:** Redis reconnect with visibility timeout; stale job recovery; DLQ for exhausted retries.

**Scaling ceiling:** Workers ≤ CPU cores (heuristic); queue depth bounded by operator policy (see capacity_planning.md); not horizontal sharding.

**Known unsafe paths:** Multiple workers without strict lock; scaling workers without fixing retry saturation; second node writing same SQLite file.

---

## T3 — degraded / offline recovery

**Supported workload:** Inspection from bundles; restore drills; read-only diagnostics; no live publish.

**Operational assumptions:** Quiesced DB; copied `OUTPUT_DIR`; no concurrent writers during restore.

**Failure domains:** Partial bundles; schema drift vs frozen contracts; restore duration growth.

**Recovery expectations:** Documented in recovery runbooks; evidence compatibility preserved by contract freeze.

**Scaling ceiling:** Restore time grows with snapshot size (see capacity_planning.md).

**Known unsafe paths:** Live restore over active DB; mixing T3 bundle with T2 live workers on same paths.

---

## T4 — unsupported experimental scaling

**Supported workload:** None for production.

**Operational assumptions:** Operator accepts total loss of support guarantees.

**Failure domains:** All distributed failure modes (split brain, dual writers, cross-region lag).

**Recovery expectations:** None documented; roll back to T1/T2.

**Scaling ceiling:** N/A — do not claim SLA.

**Known unsafe paths:** Multi-node SQLite; K8s HA without ops; active-active regions; PostgreSQL without migration program; event-bus rewrite.

See [unsupported_deployments.md](unsupported_deployments.md).
