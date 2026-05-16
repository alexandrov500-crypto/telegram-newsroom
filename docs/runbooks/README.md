# Operator recovery runbooks (v1.1)

Symptom-oriented playbooks for production-lite deployments. Complement [FAILURE_DRILLS.md](../FAILURE_DRILLS.md) (offline inspection fixtures).

| Runbook | Trigger |
|---------|---------|
| [REDIS_DOWN.md](REDIS_DOWN.md) | Queue/lock errors, Redis unreachable |
| [SQLITE_LOCKED.md](SQLITE_LOCKED.md) | `database is locked`, slow writes |
| [PARTIAL_PUBLISH.md](PARTIAL_PUBLISH.md) | Incomplete Telegram post |
| [FAILED_RESTORE.md](FAILED_RESTORE.md) | backup_cli or snapshot restore failed |
| [TELETHON_SESSION_LOST.md](TELETHON_SESSION_LOST.md) | Collector auth/session errors |
| [RETRY_STORM.md](RETRY_STORM.md) | High retry counters / worker lag |
| [DEGRADED_MODE.md](DEGRADED_MODE.md) | Safe operation with reduced dependencies |
| [SQLITE_LONG_RUNNING_MAINTENANCE.md](SQLITE_LONG_RUNNING_MAINTENANCE.md) | WAL checkpoint, long-running DB |
| [RETRY_STORM_RECOVERY.md](RETRY_STORM_RECOVERY.md) | Retry burst / DLQ saturation |
| [WAL_GROWTH.md](WAL_GROWTH.md) | WAL file growth |
| [EVIDENCE_RETENTION.md](EVIDENCE_RETENTION.md) | OUTPUT_DIR / artifact pruning |
| [LONG_RUNNING_NODE_MAINTENANCE.md](LONG_RUNNING_NODE_MAINTENANCE.md) | Monthly node hygiene |
| [MEMORY_GROWTH_INVESTIGATION.md](MEMORY_GROWTH_INVESTIGATION.md) | RSS / task growth |
| [REDIS_RECONNECT_STORM.md](REDIS_RECONNECT_STORM.md) | Transport reconnect loops |

**Opt-in reliability flags:** `WORKER_RETRY_SAFE=1`, `PUBLISH_LOCK_STRICT=1` (see [v1_1_operational_validation_report.md](../v1_1_operational_validation_report.md)).
