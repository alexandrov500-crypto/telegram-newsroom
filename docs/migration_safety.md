# Migration safety

Discipline for operator and maintainer changes without losing recoverability.

## Migration risk levels

| Level | Examples | Requirements |
|-------|----------|--------------|
| **L0** | Docs, runbooks | CI green |
| **L1** | Opt-in env flag enable | Backup + validation commands |
| **L2** | App DB Alembic migration | Quiesce + backup + rollback script |
| **L3** | Inspection contract change | Major version only + ADR |

## Rollback classes

| Class | Rollback mechanism | RTO expectation |
|-------|-------------------|-----------------|
| **A — Config** | Revert `.env` | Minutes |
| **B — Inspection** | `runtime_restore.sh` / nightly regen | Minutes–hours |
| **C — Database** | `backup_cli backup-restore` | Hours (quiesced) |
| **D — Code** | Redeploy previous tag | Minutes |

## Reversible migration requirements

- L2+ migrations MUST document reverse path or explicit "restore-only" path.
- No destructive migration without backup verification step.

## Snapshot-before-change policy

Before L1+ operator changes:

1. `python3 tools/backup_cli.py backup-create`
2. `./scripts/runtime_snapshot.sh` → dated directory
3. Record git tag / image digest

## Restore validation requirements

After restore:

```bash
make runtime-index OUTPUT_DIR=<staging>
make verify-runtime OUTPUT_DIR=<staging>
make validate-recovery OUTPUT_DIR=<staging>
```

DB restore: stop all writers first ([runbooks/SQLITE_LOCKED.md](runbooks/SQLITE_LOCKED.md)).

## Operator recovery expectations

- Migrations are **operator-driven**; no in-repo auto-heal daemons.
- Degraded mode acceptable short-term ([runbooks/DEGRADED_MODE.md](runbooks/DEGRADED_MODE.md)).
- Failed migration: stop → restore Class B or C → re-validate → postmortem.

## Related

- [evidence_lifecycle.md](evidence_lifecycle.md) · [runbooks/upgrades/](runbooks/upgrades/) · [RESTORE_PROCEDURE.md](RESTORE_PROCEDURE.md)
