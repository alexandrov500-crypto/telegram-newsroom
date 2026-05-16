# v1.1 operational validation report

**Branch:** `v1.1-chaos-validation`  
**Scope:** Controlled chaos / recovery validation (no frozen contract changes)  
**Date:** 2026-05-15

---

## Reliability improvements (opt-in, default off)

| Flag | Behavior when enabled |
|------|------------------------|
| `WORKER_RETRY_SAFE=1` | Re-enqueue before ack on retry (avoids ack-then-enqueue loss) |
| `PUBLISH_LOCK_STRICT=1` | Fail closed when Redis expected but unavailable (no silent local fallback) |

Diagnostics: `utils/reliability_diagnostics.py` — retry traces, lock events, recovery recommendations, stability evidence JSON (tests/ops only).

---

## Chaos results

| Suite | Location | Result |
|-------|----------|--------|
| Worker recovery | `tests/chaos/test_worker_recovery.py` | Pass — bounded DLQ, safe/legacy ordering, stale re-delivery |
| Publish lock | `tests/chaos/test_publish_lock_chaos.py` | Pass — strict deny, legacy fallback, contention |
| Snapshot / restore | `tests/chaos/test_snapshot_restore_chaos.py` | Pass — drills, restore script, partial tree |
| Soak / drift | `tests/chaos/test_soak_stability.py` | Pass — bounded backoff, WAL observation |
| CI matrix | `tests/chaos/test_ci_matrix.py` | Pass — flag combinations |

Run: `make chaos-test`

---

## Recovery guarantees (with opt-in flags)

| Scenario | Guarantee |
|----------|-----------|
| Transient worker error | Bounded retries → DLQ; no infinite loop |
| `WORKER_RETRY_SAFE=1` | Retry re-enqueue before ack |
| `PUBLISH_LOCK_STRICT=1` + Redis down | Publish skipped (contention path), not duplicate |
| Stale visibility lease | At-least-once re-delivery (documented) |
| Inspection restore | Deterministic replace of `OUTPUT_DIR/runtime` |

---

## Known unsafe scenarios (v1.0.0 default)

| Scenario | Risk | Mitigation |
|----------|------|------------|
| Legacy ack-before-retry + enqueue fail | Job loss | `WORKER_RETRY_SAFE=1` |
| Redis fallback + multi-worker | Duplicate publish | `PUBLISH_LOCK_STRICT=1` + fix Redis |
| Partial multi-chunk Telegram publish | Channel inconsistency | [PARTIAL_PUBLISH.md](runbooks/PARTIAL_PUBLISH.md) |
| Live DB restore | Corruption | Stop writers first |
| Multi-process SQLite | `database is locked` | Single writer |

---

## Remaining risk areas

- Live Telegram/OpenAI not exercised in CI chaos suite
- Postgres backup path still unsupported in `backup_cli`
- No automatic Telethon session in backup zip
- In-process scheduler duplicate if multiple `app.main` instances

---

## Operator confidence assessment

**Rating: B+ (production-lite, single-node, opt-in hardening)**

Operators with runbooks and nightly inspection can recover from common failures. Multi-worker production requires Redis + strict lock + safe retry enabled.

---

## Recommended production limits

| Dimension | Limit |
|-----------|-------|
| App processes | 1 scheduler owner (`app.main`) |
| SQLite writers | 1 newsroom DB writer + isolated Telethon session file |
| Workers | N only with `REDIS_ENABLED=true`, `PUBLISH_LOCK_STRICT=1`, `WORKER_RETRY_SAFE=1` |
| Inspection `OUTPUT_DIR` | One active nightly context per host |
| Chaos / soak in prod | **Disabled** — test harness only |

---

## Multi-worker safety notes

- Require Redis for queue and publish locks.
- Never run `PUBLISH_LOCK_STRICT=0` with >1 publisher unless accepting duplicate risk.
- Align `WORKER_RETRY_SAFE=1` on all workers in same queue prefix.

---

## SQLite boundary conditions

- WAL mode helps readers; not a multi-writer solution.
- Stop all processes before `backup_cli backup-restore`.
- Monitor `-wal` size during retry storms ([SQLITE_LOCKED.md](runbooks/SQLITE_LOCKED.md)).

---

## Disaster recovery confidence

| Layer | Confidence |
|-------|------------|
| `backup_cli` zip (DB + runtime json) | Medium — operator must quiesce |
| `runtime_snapshot.sh` | High for inspection tree only |
| Failure drills | High for training / CI |
| Full DC failover | Low — no in-repo HA |

---

## Recommended v1.2 priorities

1. CI backup round-trip integration test in default gate
2. RFC-001 extended metrics in production opt-in doc
3. `backup_cli --require-quiesce` guard
4. Optional deep health profile (RFC-002)
5. Postgres backup path spike (RFC-005)

---

## Related

- [post_v1_hardening.md](post_v1_hardening.md) · [runbooks/](runbooks/) · [FAILURE_DRILLS.md](FAILURE_DRILLS.md)
