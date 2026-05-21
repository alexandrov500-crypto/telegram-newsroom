# Operational resilience

Deployment integrity, publication safety, backup/recovery, and multi-runtime coordination (file-based, no Kubernetes).

## Runtime snapshot & restore

Full state archive under `{RUNTIME_STATE_DIR}/full_snapshots/`:

- Governance JSON/JSONL (`editorial/`, ledgers, policies)
- Source reputation, calibration/governance state
- Operational timeline, replay `snapshot_*.json`
- SQLite database (when `DATABASE_URL` is SQLite)
- `MANIFEST.json` with SHA-256 checksums and compatibility metadata (no secrets)

```bash
python -m tools.runtime_snapshot create
python -m tools.runtime_snapshot list
python -m tools.runtime_snapshot restore snap_YYYYMMDD_HHMMSS_<id>.tar.gz
```

Env: `RUNTIME_FULL_SNAPSHOT_MAX`, `RUNTIME_FULL_SNAPSHOT_MAX_BYTES`.

## Publication integrity

Append-only `publish_journal.jsonl` records a state machine per publish transaction:

`initiated` → `lock_acquired` → `approved` → `sending` → `sent` → `finalized`

Crash recovery uses journal + Redis/memory idempotency keys (`draft:<id>`) to prevent double-publish.

`GET /runtime/publish_journal` — recent journal tail.

## Startup validation

After env validation, `run_startup_integrity_checks` verifies writable dirs, policy JSON, migrations, publish journal inflight, queue prefix. Fatal issues emit `runtime.startup.validation.failed` and abort startup.

## Runtime migrations

Idempotent migrations tracked in `runtime_migrations.json`.

`GET /runtime/migrations`

## Leadership locks

File locks under `{RUNTIME_STATE_DIR}/locks/`:

- `runtime.lock` — process ownership
- `publish_leader.lock` — publish leader
- `scheduler_leader.lock` — scheduler leader

Stale recovery via dead PID or lease TTL. Publish requires publish leader.

## Recovery drill

Non-destructive simulation; writes `recovery_drill_report.json`:

```bash
python -m tools.recovery_drill
python -m tools.recovery_drill -o /path/to/report.json
```

## Deployment manifest

Immutable `deployment_manifest.json` + `.sha256` sidecar at startup: git SHA, config fingerprint, profile, governance version, dependency snapshot.

## Retention

Heartbeat runs `run_lifecycle_retention` for incidents, full snapshots, replay snapshots. Audit log: `retention_audit.jsonl`.

Configure via `RETENTION_*` and `RUNTIME_*` env vars.

## Operational modes

| Mode | Publish | Scheduler |
|------|---------|-----------|
| production | yes | yes |
| degraded / soak | yes | yes |
| maintenance / recovery / read_only / bootstrap | blocked | blocked* |

\* maintenance/recovery/read_only/bootstrap block scheduler ticks.

Set via `RUNTIME_OPERATIONAL_MODE` or `operational_mode.json` (reloadable).

Visible on `GET /runtime/status` under `operational_mode`.

## HTTP endpoints (ops token)

| Path | Purpose |
|------|---------|
| `/runtime/status` | Mode, leadership, deployment manifest |
| `/runtime/migrations` | Applied migrations |
| `/runtime/publish_journal` | Publish journal tail |
| `/runtime/snapshots` | Full snapshot list |
