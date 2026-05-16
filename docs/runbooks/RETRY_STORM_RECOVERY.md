# RETRY_STORM_RECOVERY

## Detection

- `retry_burst_window` high in worker heartbeat
- `RUNTIME_RETRY_STORM_COUNT` watchdog warnings
- DLQ depth growing

## Mitigation

1. Fix root dependency (OpenAI/Telegram/Redis).
2. Enable `WORKER_RETRY_SAFE=1` during recovery window.
3. Pause pipeline (`DRY_RUN` or stop scheduler) if storm continues.

## Safe restart

Restart workers after upstream healthy; drain DLQ samples first.

## Validation

- Retry counters stable over 2 intervals
- `tests/chaos` retry storm tests pass on staging config

## Rollback

Revert env flags; restore queue from backup only if corruption proven.

## Evidence collection

- DLQ entries, `retry_traces_snapshot()`, metrics counters

## Escalation thresholds

- Burst > 2× `RUNTIME_RETRY_STORM_COUNT` for 10+ minutes → incident review
