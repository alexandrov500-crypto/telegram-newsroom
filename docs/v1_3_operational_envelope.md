# v1.3 operational envelope (production-lite)

Single-node-first deployment limits after resilience engineering. **Not an SLA.**

## Maximum recommended runtime duration

| Component | Guidance |
|-----------|----------|
| `app.main` process | Restart monthly or after maintenance |
| Workers | Restart weekly with Redis queue |
| SQLite DB | Checkpoint monthly; review WAL weekly |
| Inspection `OUTPUT_DIR` | Rotate via retention; do not unbounded accumulate |

## SQLite safe boundaries

- **One writer** to newsroom DB file
- WAL expected; checkpoint when WAL > 500MB or after bulk imports
- See [runbooks/SQLITE_LONG_RUNNING_MAINTENANCE.md](runbooks/SQLITE_LONG_RUNNING_MAINTENANCE.md)

## Recommended snapshot frequency

| Artifact | Frequency |
|----------|-----------|
| `make runtime-nightly` | Daily |
| `backup_cli backup-create` | Daily (quiesced) |
| `runtime_snapshot.sh` | After nightly or before risky changes |
| Drift baseline (`RUNTIME_DRIFT_MONITOR=1`) | Weekly |

## WAL maintenance guidance

- Quiesce → `PRAGMA wal_checkpoint(TRUNCATE)`
- Avoid live restore over active DB
- [runbooks/WAL_GROWTH.md](runbooks/WAL_GROWTH.md)

## Retry storm recovery guarantees

- Bounded by `RetryPolicy.max_attempts` and deadline
- DLQ for exhausted jobs
- With `WORKER_RETRY_SAFE=1`: enqueue-before-ack on retry
- [runbooks/RETRY_STORM_RECOVERY.md](runbooks/RETRY_STORM_RECOVERY.md)

## Multi-worker operational limits

- Redis required; `PUBLISH_LOCK_STRICT=1`, `WORKER_RETRY_SAFE=1`
- Max workers: operator-defined (recommend ≤ CPU cores)
- No split-brain publish without Redis

## Evidence retention limits

- Use `tools/evidence_retention.py` + `tools/runtime_retention.py`
- Default CI artifact caps: 32 files / 168h / 500MB (prune command)
- [runbooks/EVIDENCE_RETENTION.md](runbooks/EVIDENCE_RETENTION.md)

## Safe Redis dependency expectations

- Production-lite multi-worker: Redis **required**
- Single-node dev: Redis optional with degraded semantics documented

## Production-lite scaling envelope

- 1 node, 1 DB file, N workers with Redis
- OpenAI/Telegram rate limits dominate throughput
- No horizontal app sharding in-repo

## Unsupported deployment models

- Kubernetes HA without external ops
- Multi-region active-active
- Mandatory Prometheus/Grafana
- Forced PostgreSQL migration
- Microservices split
