# SAFE_ROLLBACK

## Prerequisites

- Known-good tag or backup timestamp
- All writers stopped for Class C

## Backup requirements

- Current state backed up **before** rollback (even if broken) for forensics

## Validation steps

**Class A — config only**

1. Restore `.env`
2. Restart processes
3. Smoke: bot responds; one pipeline tick

**Class B — inspection tree**

1. `./scripts/runtime_restore.sh <snapshot_dir>`
2. `make verify-runtime OUTPUT_DIR=...`

**Class C — database**

1. Stop app + workers
2. `python3 tools/backup_cli.py backup-restore <zip>`
3. Start single writer
4. `PRAGMA integrity_check;`

**Class D — code**

1. Deploy previous container/image/tag
2. Re-run Class B/C as needed

## Rollback steps

Execute class matching failed change. Do not mix partial Class B + C without validation.

## Evidence verification

```bash
python3 tools/evidence_retention.py verify-manifest --output-dir "$OUTPUT_DIR"
```

## Degraded-mode checks

- If Redis still down, stay single-worker until [REDIS_DOWN.md](../REDIS_DOWN.md) cleared
