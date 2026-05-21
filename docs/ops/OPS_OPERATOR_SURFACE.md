# Operator control surface

Operator-facing APIs and tooling on top of resilience commit `6c76755+`.

## Authentication

Same as other ops endpoints: `OPS_HTTP_TOKEN` via query `?token=` or header `X-Ops-Token`.

## Control API (POST)

Base path: `/ops/control/`

| Endpoint | Body | Action |
|----------|------|--------|
| `POST /ops/control/mode` | `{"mode":"maintenance","reason":"..."}` | Set operational mode |
| `POST /ops/control/maintenance` | `{"reason":"..."}` | Maintenance mode |
| `POST /ops/control/recovery` | `{"reason":"..."}` | Recovery mode |
| `POST /ops/control/snapshot` | `{}` | Full runtime snapshot |
| `POST /ops/control/locks/clear` | `{}` | Clear stale file locks + re-acquire |
| `POST /ops/control/source/mute` | `{"channel":"x","minutes":60}` | Mute source |
| `POST /ops/control/source/unmute` | `{"channel":"x"}` | Unmute source |
| `POST /ops/control/editorial/freeze` | `{"reason":"..."}` | Emergency editorial freeze |
| `POST /ops/control/editorial/unfreeze` | `{}` | Release freeze |
| `POST /ops/control/leadership/rotate` | `{}` | Release + re-acquire leadership |
| `POST /ops/control/replay` | `{"hours":24}` | Recovery drill + transparency bundle |
| `POST /ops/control/status` | `{}` | Control status |

Optional header: `X-Correlation-ID`. All actions append to `ops/action_journal.jsonl`.

## Audit

`GET /runtime/audit/search?entity=suppression&since_unix=...&limit=50&offset=0`

Entities: `publish`, `suppression`, `operator_action`, `policy_match`, `drift_warning`, `anomaly`, `calibration`, `runtime_recovery`, `control_action`, `timeline`.

## Analytics

`GET /runtime/analytics/publication?days=14`

Daily rollups in `analytics/publication_daily.json`.

## Dashboard payloads

- `GET /runtime/dashboard/overview`
- `GET /runtime/dashboard/editorial`
- `GET /runtime/dashboard/incidents`
- `GET /runtime/dashboard/publication`

Stable `schema_version: 1` JSON for future UI.

## Transparency

`GET /runtime/transparency/export?hours=24`

## CLI

```bash
python -m tools.generate_ops_report --hours 24
python -m tools.rollback_runtime list
python -m tools.rollback_runtime compare snap_YYYYMMDD_HHMMSS_xxx.tar.gz
python -m tools.rollback_runtime rollback snap_xxx.tar.gz --dry-run
```

## Notifications

Queued to `ops/pending_notifications.jsonl`, flushed on heartbeat to admin Telegram chat. Rate-limited and deduplicated.

Kinds: `runtime_degraded`, `publish_halted`, `editorial_drift`, `snapshot_failed`, `operational_mode_changed`.
