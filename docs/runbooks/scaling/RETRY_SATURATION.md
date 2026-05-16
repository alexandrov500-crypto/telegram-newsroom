# RETRY_SATURATION

## Detection

- `retry_burst_window` ≥ `RUNTIME_RETRY_STORM_COUNT`
- DLQ growth; repeated job failures in logs
- Scalability diagnostics `retry_saturation` finding

## Mitigation

1. Identify failing job kind and root exception
2. Fix upstream (token, API, content policy)
3. Temporarily reduce worker count to 1
4. Do not increase `max_attempts` without review

## Safe scaling guidance

- **Never** add workers during saturation — retry amplification
- Enable `WORKER_RETRY_SAFE=1` before returning to multi-worker

## Rollback

- Revert env changes that increased retry aggressiveness
- Clear poison jobs to DLQ after manual review

## Evidence collection

- Worker runtime diag export
- DLQ entries (redacted if `SECURITY_REDACTION=1`)

## Escalation thresholds

| Signal | Action |
|--------|--------|
| Burst at threshold > 15 min | P1 — stop scale-out |
| DLQ rate doubling hourly | Contain enqueue |
| Unknown root cause | Architecture + security review |
