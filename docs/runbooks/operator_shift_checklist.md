# Operator shift checklist

Read-only reviews at shift start/end. No automated actions from tooling output.

## Shift start

| Step | Command / doc | ☐ |
|------|---------------|---|
| Diagnostics review | `make live-telegram-diagnostics` | |
| Snapshot baseline | `python3 tools/ops_metrics_snapshot.py --rotate` | |
| Queue review | `python3 tools/queue_introspection.py` | |
| Retry review | Check `retry_burst_window`, `publish_retries` in diagnostics | |
| Publish caps | Confirm `PUBLISH_BURST_*`, ≤5/day policy | |
| Env verify | `python3 tools/staging_environment_verify.py --strict` | |
| Rollback ready | Know `DRY_RUN=true` + stop command | |

## Shift end

| Step | Action | ☐ |
|------|--------|---|
| Incident summary | Log MEDIUM+ in ops log; postmortem if needed | |
| Unresolved retries | Note DLQ depth + failed drafts | |
| Diagnostics export | `tools/ops_metrics_snapshot.py` + optional timeline report | |
| Handoff | `python3 tools/generate_shift_handoff.py` | |
| Analytics rollup | `python3 tools/ops_analytics_aggregate.py` | |
| Charts | `python3 tools/ops_visualize.py` | |

## Emergency

| Situation | Immediate action |
|-----------|------------------|
| Duplicate suspicion | `DRY_RUN=true`; channel + DB inspect; [incident_response.md](incident_response.md) |
| Reconnect storm | Pause collector; session runbook; diagnostics HIGH |
| FloodWait escalation | Pause publishes; increase intervals; wait cooldown |
| Redis unavailable | Single worker only; strict lock implications |

## Tooling constraints (ADR-030)

- Tools are **read-only** — never script dequeue/retry/publish from output
- Escalation is **manual**

## Related

- [controlled_activation.md](controlled_activation.md)
- [alerting_baseline.md](../operations/alerting_baseline.md)
