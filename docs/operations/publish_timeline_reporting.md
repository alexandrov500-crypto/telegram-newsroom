# Publish timeline reporting

Offline report built from metrics snapshots and optional `operational_timeline.json`.

## Usage

```bash
# Capture snapshots first
python3 tools/ops_metrics_snapshot.py --rotate

# Report
python3 tools/publish_timeline_report.py
python3 tools/publish_timeline_report.py --json-output report.json --markdown-output report.md
```

## Inputs

| Source | Path |
|--------|------|
| Metrics snapshots | `var/ops_history/ops_metrics_*.json` |
| Operational timeline | `RUNTIME_STATE_DIR/operational_timeline.json` |

**No live Telegram API** — works from files only.

## Outputs

- **JSON:** trends (`telethon_flood_waits_delta`, reconnect, publish retries), `retry_burst_max`, timeline events
- **Markdown:** human summary for shift handoff

## Bounded memory

- Default last **96** snapshots (`--limit`)
- Timeline tail capped at 48 publish-related events in report

## Corruption handling

Invalid snapshot JSON → exit code **1** with error message. Fix or remove corrupt file under `var/ops_history/`.

## Related

- [72h_operational_findings.md](72h_operational_findings.md)
- [production_baselines.md](production_baselines.md)
