# Maintenance matrix

Long-term operational cadence for production-lite deployments.

## Daily

| Task | Command / doc |
|------|----------------|
| Nightly inspection | `make runtime-nightly` |
| Index + verify | `make runtime-index`, `make verify-runtime` |
| Review WARNING vs FAIL | [OPERATOR_QUICKSTART.md](OPERATOR_QUICKSTART.md) |

## Weekly

| Task | Command / doc |
|------|----------------|
| DB + evidence backup | `backup_cli backup-create` |
| Runtime snapshot | `scripts/runtime_snapshot.sh` |
| Evidence size report | `tools/evidence_retention.py report` |
| Failure drill (rotate) | [FAILURE_DRILLS.md](FAILURE_DRILLS.md) |
| Optional drift compare | `RUNTIME_DRIFT_MONITOR=1` |

## Monthly

| Task | Command / doc |
|------|----------------|
| SQLite WAL checkpoint | [runbooks/SQLITE_LONG_RUNNING_MAINTENANCE.md](runbooks/SQLITE_LONG_RUNNING_MAINTENANCE.md) |
| Process restart (app + workers) | [runbooks/LONG_RUNNING_NODE_MAINTENANCE.md](runbooks/LONG_RUNNING_NODE_MAINTENANCE.md) |
| Prune CI/artifact dirs | `tools/evidence_retention.py prune --dry-run` then apply |
| Review CHANGELOG / deps | [DEPENDENCY_POLICY.md](DEPENDENCY_POLICY.md) |

## Per-release (maintainers)

| Task | Command |
|------|---------|
| Full gate | `make release-check` |
| Minor gate | `make resilience-validate` |
| Readiness | `python3 tools/release_readiness.py --strict` |
| Update CHANGELOG | [RELEASE_PROCESS.md](RELEASE_PROCESS.md) |

## Incident-response

| Task | Doc |
|------|-----|
| Triage | [ISSUE_TRIAGE.md](ISSUE_TRIAGE.md) |
| Redis down | [runbooks/REDIS_DOWN.md](runbooks/REDIS_DOWN.md) |
| Retry storm | [runbooks/RETRY_STORM_RECOVERY.md](runbooks/RETRY_STORM_RECOVERY.md) |
| Failed restore | [runbooks/FAILED_RESTORE.md](runbooks/FAILED_RESTORE.md) |
| Rollback | [runbooks/upgrades/SAFE_ROLLBACK.md](runbooks/upgrades/SAFE_ROLLBACK.md) |

## Recovery validation cadence

| Event | Validation |
|-------|------------|
| After restore | `verify-runtime`, `validate-recovery` |
| After minor upgrade | [runbooks/upgrades/MINOR_UPGRADE.md](runbooks/upgrades/MINOR_UPGRADE.md) |
| After patch | [runbooks/upgrades/PATCH_UPGRADE.md](runbooks/upgrades/PATCH_UPGRADE.md) |

## Chaos validation cadence

| Audience | Cadence |
|----------|---------|
| CI / PR (chaos paths) | Every PR touching workers/locks |
| Maintainers pre-minor | `make chaos-test` |
| Operators | Optional drill quarterly |

## Soak validation cadence

| Audience | Cadence |
|----------|---------|
| CI | `make soak-test` on soak path PRs |
| Staging | `make soak-validate` before minor tag |
| Production | Observe envelope ([v1_3_operational_envelope.md](v1_3_operational_envelope.md)) |

## Related

- [MAINTENANCE_MODE.md](MAINTENANCE_MODE.md) · [release_governance.md](release_governance.md)
