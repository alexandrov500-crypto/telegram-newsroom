# MINOR_UPGRADE

## Prerequisites

- Read [CHANGELOG.md](../../../CHANGELOG.md) deprecations
- Read [feature_flag_governance.md](../../feature_flag_governance.md)
- Staging burn-in recommended ([BURN_IN_REPORT.md](../../BURN_IN_REPORT.md))

## Backup requirements

- Full `backup_cli` zip
- `runtime_snapshot.sh` dated copy
- Export current `.env` (secrets store offline)

## Validation steps

```bash
python3 tools/release_readiness.py --strict
make resilience-validate    # maintainers
```

On staging after deploy:

```bash
make runtime-nightly
make runtime-index && make verify-runtime && make validate-recovery
OUTPUT_DIR=./runtime_ops_output STRICT=0 ./scripts/runtime_sanity_check.sh
```

## Rollback steps

[SAFE_ROLLBACK.md](SAFE_ROLLBACK.md) — redeploy previous tag + restore backup if DB migrated.

## Evidence verification

- 12 required artifacts present
- Manifest checksums OK
- Optional baseline/drift WARNING acceptable if documented

## Degraded-mode checks

- Enable `WORKER_RETRY_SAFE` / `PUBLISH_LOCK_STRICT` only after Redis healthy
- Run [EXPERIMENTAL_FLAG_ENABLE.md](EXPERIMENTAL_FLAG_ENABLE.md) on staging first
