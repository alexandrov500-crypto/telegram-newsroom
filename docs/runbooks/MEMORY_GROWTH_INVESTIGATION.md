# MEMORY_GROWTH_INVESTIGATION

## Detection

- `memory_growth` drift finding
- `ANOMALY_MEMORY_RSS_BYTES_WARN` logs

## Mitigation

1. Capture `utils/resource_stability.snapshot_resources()` samples.
2. Restart process during maintenance window.
3. Reduce soak/tick frequency if self-inflicted.

## Safe restart

Graceful shutdown via systemd/Docker; verify no orphan workers.

## Validation

RSS stable over 24h at steady load.

## Rollback

N/A — observational.

## Evidence collection

- Resource trend JSON from soak harness
- Asyncio task counts if logged

## Escalation thresholds

- RSS doubles in <7 days at flat traffic → code review / leak hunt
