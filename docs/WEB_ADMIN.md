# Lightweight web admin (server-rendered)

There is **no React SPA**. The admin surface is:

1. **Telegram bot** (primary moderation UX)
2. **Optional asyncio HTTP** on `HEALTH_HTTP_PORT` (same process as `python -m app.main`)

## Authentication

Set `OPS_HTTP_TOKEN` to protect `/ops*`, `/ops.json`, and `/metrics`. Pass `?token=...` or header `X-Ops-Token: ...`.

## Pages (HTML)

All routes are **read-only** (except nothing mutates via HTTP — moderation stays in Telegram).

| URL | Description |
|-----|-------------|
| `/ops` | Runtime + editorial JSON excerpts, warnings, timeline |
| `/ops/search?topic=…&entity=…&fingerprint=…&suppression=…&status=…` | DB substring search |
| `/ops/dlq` | Per-job-kind DLQ samples |
| `/ops/draft/<id>` | Explain + diff + edit history |
| `/ops/why/<id>/suppressed` | Suppression reasons |
| `/ops/why/<id>/escalated` | Escalation context |
| `/ops/why/<id>/relevance` | Relevance JSON |
| `/ops/trace/<id>/policy` | Policy notes + raw `pipeline_decision` |
| `/ops/trace/<id>/cadence` | Cadence gate preview |
| `/ops/breakdown/<id>` | Structured explanation dict |

## Machine-readable

- `/ops.json` — same payload as `export-ops-dashboard` CLI JSON mode
- `/metrics` — Prometheus text exposition

## Implementation notes

- Routing lives in `app/ops_http_routes.py`; the TCP server is `app/health_http.py`.
- DLQ listing calls `get_reliable_transport()` — the bot process initializes reliable transport at startup (`app/main.py`) so DLQ pages work when workers use Redis or in-memory transport.
