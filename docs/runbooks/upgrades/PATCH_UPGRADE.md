# PATCH_UPGRADE

## Prerequisites

- Current tag documented
- Staging optional for critical patches

## Backup requirements

- `backup_cli backup-create` if DB or pipeline code touched
- `runtime_snapshot.sh` if inspection tooling touched

## Validation steps

```bash
make ci-test          # maintainers
make release-check    # maintainers
make runtime-index OUTPUT_DIR=./runtime_ops_output
make verify-runtime OUTPUT_DIR=./runtime_ops_output
```

## Rollback steps

See [SAFE_ROLLBACK.md](SAFE_ROLLBACK.md) Class A or D.

## Evidence verification

- `verify-runtime` status unchanged or improved
- No new required JSON files vs [RUNTIME_CONTRACTS.md](../../architecture/RUNTIME_CONTRACTS.md)

## Degraded-mode checks

- Confirm `REDIS_ENABLED` / strict flags unchanged unless release notes say otherwise
