# Known limitations (v1.0.0)

Explicit boundaries for production-lite operation. Not defects — scope choices.

## SQLite

- **Single writer** recommended; multiple processes on one DB file risk corruption.
- Not a multi-tenant or high-concurrency warehouse.
- Backup via `backup_cli` before upgrades.

## Single-node assumptions

- One deployment, one `RUNTIME_STATE_DIR`, one inspection `OUTPUT_DIR` per nightly context.
- No in-repo distributed coordination, leader election, or shard routing.

## No HA guarantees

- No automatic failover, hot standby, or zero-downtime guarantees.
- Process restart is manual (systemd/Docker restart policies are operator-owned).

## No distributed coordination

- Optional Redis/Postgres are documented scaling paths — not required for production-lite.
- Frozen governance artifacts describe single-node semantics only.

## Manual recovery expectations

- Operators run `make runtime-nightly`, `backup_cli`, and inspection CLIs deliberately.
- Tools do not auto-heal production state or mutate live pipeline JSON during validation.

## Operator skill level

Expected:

- Comfortable with shell, `.env`, `make`, reading JSON status fields
- Can distinguish `OUTPUT_DIR` vs `RUNTIME_STATE_DIR` vs DB path
- Reads `FAIL` / `WARNING` summaries and [FAILURE_DRILLS.md](FAILURE_DRILLS.md)

## Production-lite scope boundaries

| In scope | Out of scope |
|----------|----------------|
| Telegram newsroom pipeline | Platform control plane |
| Offline inspection | Prometheus/Grafana mandate |
| `backup_cli` zip restore | K8s disaster recovery playbooks in-repo |
| Failure drills | Automated remediation daemons |

## Enterprise SLA

**None.** Community maintenance per [SUPPORT.md](../SUPPORT.md) and [LTS_NOTES.md](LTS_NOTES.md).

## Related

- [MAINTENANCE_MODE.md](MAINTENANCE_MODE.md) · [STABILITY_GUARANTEES.md](STABILITY_GUARANTEES.md)
