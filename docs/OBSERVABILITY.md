# Operational observability (production-lite)

This project avoids a full APM stack. Observability is **read-heavy**, **JSON-first**, and safe to export.

## Runtime warnings

`observability/runtime_warnings.py` aggregates deterministic warnings from:

- in-process metrics counters (`utils.metrics.export_snapshot`)
- `gather_runtime_health` queue depths and readiness

Consumers: merged **operational dashboard** bundle and optional HTTP `/ops`.

## Dashboard bundle

`dashboard/build_operational_dashboard_bundle` (see `dashboard/__init__.py`) merges:

- `build_runtime_dashboard` — health, metrics export, recent runtime events
- `build_editorial_dashboard` — editorial intelligence report slice
- `collect_runtime_warnings`
- timeline tail from `dashboard/timeline.py` (`operational_timeline.json` under `RUNTIME_STATE_DIR`)

## Timeline snapshots

`append_timeline_event` appends small JSON rows (cluster defer/suppress, duplicate skip, draft created, publish cadence block, publication ok). No event-sourcing framework — a bounded JSON list only.

## Prometheus text

`GET /metrics` returns **Prometheus exposition format** built from `utils.prometheus_export.render_prometheus_metrics` over the in-process snapshot. No Prometheus server is required; any scraper can pull text.

## HTTP surface

When `HEALTH_HTTP_PORT > 0`, the asyncio server in `app/health_http.py` exposes:

| Path | Purpose |
|------|---------|
| `/health` / `/healthz` | liveness |
| `/ready` / `/readiness` | readiness (`gather_runtime_health`) |
| `/ops.json` | full dashboard bundle JSON |
| `/ops` | minimal HTML overview + links |
| `/ops/search` | draft search (query params) |
| `/ops/dlq` | DLQ sample tables (requires reliable transport init) |
| `/ops/draft/<id>` | draft explain + diff + edit history |
| `/ops/why/<id>/{suppressed,escalated,relevance}` | focused explain pages |
| `/ops/trace/<id>/{policy,cadence}` | policy / cadence traces |
| `/ops/breakdown/<id>` | structured pipeline breakdown |
| `/metrics` | Prometheus text |

Optional `OPS_HTTP_TOKEN`: when set, `/ops*`, `/ops.json`, and `/metrics` require matching `?token=` or `X-Ops-Token` header.

## CLI export

```bash
python -m tools.admin_cli export-ops-dashboard --out var/reports/ops.json --format json
python -m tools.admin_cli export-ops-dashboard --out var/reports/ops.html --format html
```

HTML uses `utils/operational_reports.render_operational_html_bundle` (single static file).
