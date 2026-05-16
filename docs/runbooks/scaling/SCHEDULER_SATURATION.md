# SCHEDULER_SATURATION

## Detection

- `SCHEDULER_DIAGNOSTICS=1` overlap detection
- Pipeline jobs stacking; missed intervals
- `scheduler_saturation` finding in scalability diagnostics

## Mitigation

1. Increase interval between heavy jobs if configurable
2. Reduce concurrent worker load during scheduler window
3. Profile long-running job handlers

## Safe scaling guidance

- Adding workers does not fix scheduler overlap on single process
- Split schedules across maintenance windows instead

## Rollback

- Revert schedule config changes
- Disable non-critical scheduled jobs temporarily

## Evidence collection

- Scheduler diagnostics snapshot
- Job duration logs (redacted)

## Escalation thresholds

| Condition | Action |
|-----------|--------|
| Overlap every run | Change schedule or job scope |
| Missed nightly inspection | P2 ops |
| Requires distributed scheduler | T4 — not in-repo |
