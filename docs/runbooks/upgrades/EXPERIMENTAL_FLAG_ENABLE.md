# EXPERIMENTAL_FLAG_ENABLE

## Prerequisites

- Staging environment
- [feature_flag_governance.md](../../feature_flag_governance.md) read
- Redis available if enabling `PUBLISH_LOCK_STRICT` with multi-worker

## Backup requirements

- Snapshot + backup before flag change

## Validation steps

1. Set one flag at a time:
   - `WORKER_RETRY_SAFE=1`
   - `PUBLISH_LOCK_STRICT=1` (with `REDIS_ENABLED=true`)
   - `RUNTIME_DRIFT_MONITOR=1` (diagnostic only)
   - `SCHEDULER_DIAGNOSTICS=1` (diagnostic only)
2. Restart affected processes
3. `make chaos-test` on staging maintainers image OR run worker publish smoke
4. `python3 tools/release_readiness.py --check-env`

## Rollback steps

- Set flag `=0` or remove from `.env`
- Restart processes

## Evidence verification

- Drift fingerprint reflects new config when monitor enabled
- No unexpected `verify-runtime` FAIL

## Degraded-mode checks

- `python3 tools/release_readiness.py --check-env` warns on incompatible combos
