# Auditability and incident traceability

Bounded, operator-readable trace chains without secret leakage.

## Correlation identifiers

| ID | Source | Use |
|----|--------|-----|
| `event_id` | `utils/structured_log.log_event` | Per log line |
| `correlation_id` | `utils/operational_context` | Cross-service operator trace |
| `tick_id` | Pipeline `begin_pipeline_tick` | Scheduler/pipeline scope |
| `delivery_id` | Worker transport | Job retry / DLQ |

## Incident trace chains

Recommended grep order:

1. `correlation_id` from incident window
2. `delivery_id` for worker failures
3. `event_id` for single log line drill-down

## Audit event classification

| Class | Examples |
|-------|----------|
| **security_sensitive** | Token rotation, restore, strict lock denial |
| **operational** | nightly, verify-runtime, backup |
| **diagnostic** | drift report, soak harness |

Mark sensitive actions in logs with field `security_sensitive=true` (convention for operators adding custom log_event calls).

## Recovery trace

- `utils/reliability_diagnostics.retry_traces_snapshot()` — retry ordering evidence
- DLQ samples via `/ops/dlq` — redact before export

## Verbosity bounds

- `LOG_MAX_FIELD_LEN` caps field size
- Runtime events ring buffer maxlen 256
- No full payload logging for OpenAI/Telegram bodies in production

## Related

- [secrets_hygiene.md](secrets_hygiene.md)
