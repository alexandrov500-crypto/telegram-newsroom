# Production burn-in report (v1.0.0)

Operational evidence template for running the newsroom under **production-lite** conditions over multiple nightly cycles. No new architecture — validation and discipline only.

## 7-day burn-in checklist

| Day | Operator actions | Pass criteria |
|-----|------------------|---------------|
| 1 | `make install-dev`, `.env`, `bash deploy/bootstrap.sh`, start `app.main` | Process healthy; DB writable |
| 1 | `make runtime-preflight` | Exit 0 |
| 1 | `make runtime-nightly` | `OUTPUT_DIR/runtime/*` populated |
| 2–6 | Scheduled nightly + live pipeline | No unhandled crashes; logs reviewed |
| Daily | `scripts/runtime_sanity_check.sh` | Required files present; review CLI status |
| Daily | `scripts/runtime_snapshot.sh` | Snapshot archived under `var/backups/runtime_snapshots/` |
| Weekly | `python tools/backup_cli.py backup-create` | Zip validates |
| 7 | `make release-check` (maintainer) | Contracts + quality green |
| 7 | Fill **Evidence log** below | Trends documented |

## Expected runtime outputs (after nightly)

Under `OUTPUT_DIR/runtime/` (default `./runtime_ops_output`):

- 12 required JSON files + optional `runtime_baseline.json`, `drift_report.json`
- Last written: `runtime_index.json` with `index_status` OK or explainable WARNING
- Sidecars at `OUTPUT_DIR` root: `runtime_bundle.zip`, `qualification.json` (when pipeline succeeds)

**Good output:** `make runtime-index` → `Index status: OK`, no missing required in lifecycle list.

## Disk growth expectations

| Area | Growth driver | Bound |
|------|---------------|-------|
| `OUTPUT_DIR/runtime/` | Latest-only JSON (~tens of KB per nightly) | Overwritten each nightly |
| `OUTPUT_DIR/runtime_bundle.zip` | Soak/benchmark payload | One zip per run |
| `RUNTIME_STATE_DIR` | Live editorial JSON | Retention + `backup_cli` |
| SQLite DB | Raw posts, drafts | `RETENTION_*` env |
| Snapshots | `runtime_snapshot.sh` | Operator prunes `var/backups/runtime_snapshots/` |

No unbounded artifact archive in-repo — operators prune archives.

## Operator validation steps

```bash
export OUTPUT_DIR=./runtime_ops_output
make runtime-nightly RUNTIME_DIR=./var/runtime OUTPUT_DIR="$OUTPUT_DIR"
scripts/runtime_sanity_check.sh
STRICT=1 scripts/runtime_sanity_check.sh   # exit non-zero on WARNING/FAIL
make verify-runtime OUTPUT_DIR="$OUTPUT_DIR"
```

## Evidence log (fill during burn-in)

| Date | Nightly OK? | index_status | verify | recovery | Notes |
|------|-------------|--------------|--------|----------|-------|
| | | | | | |
| | | | | | |

## Failure drills

Practice: [FAILURE_DRILLS.md](FAILURE_DRILLS.md) · fixtures: [examples/failure_drills/](../examples/failure_drills/).

## Restore

Database + runtime state: [RESTORE_PROCEDURE.md](RESTORE_PROCEDURE.md) · inspection-only tree: `scripts/runtime_restore.sh`.

## Related

- [OPERATIONAL_CONFIDENCE.md](OPERATIONAL_CONFIDENCE.md) · [REAL_WORLD_VALIDATION.md](REAL_WORLD_VALIDATION.md)
