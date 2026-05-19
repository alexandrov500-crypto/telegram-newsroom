# Operational Forensics & Resilience

Long-running canary operation requires durable audit trails, incident reconstruction, and drift detection — not feature expansion.

## Core artifacts

| Artifact | Table / path | Purpose |
|----------|----------------|---------|
| Incident timeline | `live_incident_timeline` | Chronological operational events |
| Operational audit | `live_operational_audit` | Append-only accountability log |
| Runtime snapshots | `runtime_state_snapshot` | Point-in-time runtime drift analysis |
| Locked baseline | `ops_runtime_baseline` | Day-0 comparison anchor |
| Incident bundles | `var/ops/incident_bundles/` | Permanent RCA exports |
| Observation pulses | `var/ops/pulses/` | 48h observation cadence (30d file retention) |

## Correlation IDs

Every publish receives a correlation ID (`pub_<hex>`) propagated through:

- publish guard decisions (`live_publish_trace.correlation_id`)
- incident timeline events
- operational audit entries
- Telegram alerts (`runtime_instance_id` + correlation in details when bound)

Query end-to-end:

```bash
curl "http://127.0.0.1:8080/incident_timeline?correlation_id=pub_abc123"
curl "http://127.0.0.1:8080/operational_audit?correlation_id=pub_abc123"
```

## HTTP endpoints

- `GET /incident_timeline` — filters: `since`, `until`, `event_type`, `correlation_id`, `publish_id`, `limit`
- `GET /operational_audit` — filters: `publish_id`, `correlation_id`, `limit`
- `GET /observation_pulse` — current pulse + drift warnings
- `GET /runtime_identity` — active runtime instance

## Incident workflow

1. **Detect** — observation pulse severity `critical`, drift warning, or operator alert
2. **Freeze** — `/freeze_publishing` immediately
3. **Reconstruct** — `GET /incident_timeline`, `/publish_trace/{id}`, replay script
4. **Bundle** — `python3 scripts/export_incident_bundle.py --incident INC-001 --publish-id 4`
5. **Analyze** — logs in bundle, traces, snapshots; no live republish
6. **Resume** — `/resume_live` only after root cause understood

Rule: **freeze first → analyze second → resume later**

## Forensic replay (read-only)

```bash
python3 scripts/replay_publish_trace.py --id 4
```

Reconstructs source input, guard scores, timeline, and audit log. **Does not send to Telegram.**

## Operational drift

Locked baseline compared on each observation pulse. Warnings logged as:

`event=operational_drift_detected metric=publish_latency baseline=0.7 current=2.1`

Lock Day-0 baseline:

```bash
python3 scripts/ops_lock_baseline.py --notes "canary day-0"
```

Tune via env: `DRIFT_LAG_MULTIPLIER`, `DRIFT_PUBLISH_LATENCY_MULT`, `DRIFT_TRUST_DROP`, `DRIFT_RECOVERY_DELTA`

## Runtime snapshots

Background task `forensics-runtime-snapshot` (default every 300s, `RUNTIME_SNAPSHOT_INTERVAL_SEC`).

Disable with `OPS_FORENSICS_ENABLED=false`.

## Retention policy

| Artifact | Retention |
|----------|-----------|
| Publish traces | Long-term (existing `live_publish_trace`) |
| Operational audit | Long-term (append-only, no prune) |
| Incident timeline | 30 days (configurable prune) |
| Runtime snapshots | 30 days |
| Metrics snapshots | 90 days |
| Incident bundles | Permanent on disk |
| Observation pulses (files) | 30 days (manual) |
| Replay artifacts | Ephemeral (stdout / bundle export) |

Apply DB prune (dry-run first):

```bash
python3 scripts/ops_forensics_retention.py
python3 scripts/ops_forensics_retention.py --apply
```

## Event types (timeline)

- `publish_started`, `publish_succeeded`, `publish_failed`
- `freeze_publishing`, `resume_live`
- `mark_good_post`, `mark_bad_post`
- `source_quarantine`
- `watchdog_alert`, `loop_stalled`, `runtime_recovery`
- `operational_drift_detected`

## Escalation

1. `/freeze_publishing`
2. `python3 scripts/runtime_process_check.py`
3. `python3 scripts/export_incident_bundle.py --incident <id> --publish-id <n>`
4. Inspect `var/log/pilot-operator.log`
5. Do not change `RUNTIME_PROFILE`, throughput, or re-enable research loops during investigation

## Constraints (canary phase)

- `LIVE_MODE=canary`
- `LIVE_CANARY_MAX_PER_HOUR=3`
- `RUNTIME_PROFILE=minimal_pilot`
- No autonomous publishing
- No research loop re-enable
