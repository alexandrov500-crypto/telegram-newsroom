# Production observability & incident ops

Baseline: operational hardening `441c726` + observability layer (timeline, incidents, `/runtime/*`).

## Structured logs (normalized JSON)

Each `log_event()` line is a single JSON object:

```json
{
  "timestamp": "2026-05-20T21:30:00Z",
  "level": "INFO",
  "event": "scheduler.tick.completed",
  "subsystem": "scheduler",
  "runtime_id": "831cc638-da0f-4d3b-bb29-af7b55a331f4",
  "git_sha": "441c726",
  "build_version": "3.0.0",
  "uptime_sec": "1842.5",
  "tick_id": "tick-12-…",
  "wall_sec": 36.8
}
```

Enable redaction: `SECURITY_REDACTION=1` in production.

## HTTP endpoints (read-only)

Same auth as `/ops` when `OPS_HTTP_TOKEN` is set (`?token=` or `X-Ops-Token`).

| Path | Description |
|------|-------------|
| `GET /health` | Liveness + `runtime` block (queue, circuit, polling) |
| `GET /runtime/status` | Aggregate runtime status |
| `GET /runtime/watchdog` | Stall/burst/lag signals |
| `GET /runtime/queues` | Queue depths + overflow counter |
| `GET /runtime/circuit` | OpenAI circuit snapshot |
| `GET /runtime/timeline` | In-memory timeline (newest first) |
| `GET /runtime/incidents` | Recent `*.tar.gz` under `{runtime_state_dir}/incidents/` |
| `GET /metrics` | Prometheus text |

### Examples

```bash
curl -s http://127.0.0.1:8080/runtime/status | jq
curl -s http://127.0.0.1:8080/runtime/timeline | jq '.entries[:5]'
curl -s 'http://127.0.0.1:8080/runtime/circuit' | jq
```

## Automatic incident bundles

**Directory:** `{RUNTIME_STATE_DIR}/incidents/` (e.g. `/data/runtime/incidents/` on VPS).

**Triggers (with cooldown, default 15 min):**

| Trigger | Condition |
|---------|-----------|
| `watchdog_exception_burst` | Watchdog exception burst |
| `queue_overflow_burst` | Repeated queue overflow |
| `openai_failure_burst` | Many OpenAI failures in window |
| `watchdog_scheduler_stalled` | Scheduler stall |
| `watchdog_collector_stalled` | Collector stall |
| `runtime_degradation` | SLO dependency → degraded |

**Bundle contents:** `manifest.json`, `health.json`, `metrics.json`, `circuit.json`, `timeline.json`, `logs_recent.txt`, `env_whitelist.json` (no secrets).

**Retention:** `INCIDENT_RETENTION_COUNT` (default 24), `INCIDENT_RETENTION_MAX_BYTES` (default 50MB).

**Manual bundle (legacy):**

```bash
bash /opt/newsroom/tools/debug_telegram_runtime.sh /tmp/manual-incident.tar.gz
```

**In-process sample (dev):**

```bash
python3 -c "
from pathlib import Path
from ops.incidents.bundle import write_incident_bundle_sync
p = write_incident_bundle_sync(incidents_dir=Path('var/runtime/incidents'), trigger='sample', detail={'note': 'dry_run'})
print(p)
"
```

## Recovery telemetry

| Event | Meaning |
|-------|---------|
| `openai.circuit.half_open` | Probe window started |
| `runtime.recovery.probe` | Lifecycle mirror of half-open |
| `openai.circuit.closed` | Circuit closed after success |
| `runtime.recovered.full` | Full AI path restored |

Histograms: `recovery_duration_seconds`, `degradation_duration_seconds`.

## Soak summary

Every `operational_report_interval_hours` (default 4h): log line `ops.soak.summary` with uptime, RSS, queue depth, scheduler cycles, collector throughput, circuit state, watchdog alert count.

## Env knobs

| Variable | Default |
|----------|---------|
| `INCIDENT_TRIGGER_COOLDOWN_SEC` | 900 |
| `INCIDENT_OPENAI_FAIL_THRESHOLD` | 8 |
| `INCIDENT_QUEUE_OVERFLOW_THRESHOLD` | 3 |
| `INCIDENT_RETENTION_COUNT` | 24 |

See also: [PRODUCTION_SOAK_7DAY.md](./PRODUCTION_SOAK_7DAY.md), [METRICS_CARDINALITY.md](./METRICS_CARDINALITY.md).
