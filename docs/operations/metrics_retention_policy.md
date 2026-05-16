# Metrics retention policy

Lifecycle for ops metrics snapshots (ADR-030 + ADR-031). **Not** runtime `runtime/*.json` artifacts.

## Active snapshots (`var/ops_history/`)

| Rule | Value |
|------|-------|
| Max files | 200 (default `rotate_snapshots`) |
| Max total size | 20 MB |
| Filename pattern | `ops_metrics_*.json` |
| Schema | `OPS_SNAPSHOT_SCHEMA_VERSION = 1` |

**Capture cadence:** operator / cron every 4h recommended (72h window).

```bash
python3 tools/ops_metrics_snapshot.py --rotate
```

## Archive (`var/ops_archive/`)

| Rule | Value |
|------|-------|
| Trigger | Snapshots older than **14 days** (default) |
| Format | `YYYY-MM/<name>.json.gz` |
| Integrity | gzip + JSON schema check |
| Per-run byte cap | 50 MB (archive stops if exceeded) |

```bash
python3 tools/ops_archive.py --older-than-days 14 --rotate
python3 tools/ops_archive.py --verify-only
```

## Reports (`var/ops_reports/`)

| Artifact | Regenerable |
|----------|-------------|
| `analytics_summary.json` | Yes |
| `analytics_summary.md` | Yes |
| `*.svg` | Yes |
| `shift_handoff.md` | Yes |

Safe to delete entire directory.

## Compression policy

- Active history: uncompressed JSON (fast append)
- Archive: gzip level default (stdlib)
- No tarballs required for P2

## Corruption handling

| Stage | Behavior |
|-------|----------|
| Analytics load | Skip file; list in `skipped_corrupt` |
| Archive verify | Reject archive file; keep source snapshot |
| CLI corrupt input | Exit non-zero when all inputs invalid |

## Cleanup strategy

1. **Daily:** `ops_metrics_snapshot.py --rotate`
2. **Weekly:** `ops_archive.py` + `--verify-only`
3. **Ad hoc:** delete `var/ops_reports/` to reclaim disk

## Disk usage limits (production-lite T1)

| Path | Expected |
|------|----------|
| `var/ops_history/` | < 20 MB |
| `var/ops_archive/` | < 100 MB operator target |
| `var/ops_reports/` | < 5 MB |

## Related

- [ADR-031](../architecture/ADR-031-operational-analytics-layer.md)
- [72h_operational_findings.md](72h_operational_findings.md)
