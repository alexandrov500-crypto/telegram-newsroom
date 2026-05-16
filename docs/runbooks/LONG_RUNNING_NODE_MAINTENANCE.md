# LONG_RUNNING_NODE_MAINTENANCE

## Detection

- Node uptime > 30 days without maintenance
- RSS drift warnings, scheduler lag reports

## Mitigation

Weekly: `make runtime-nightly`, `make chaos-validate`, optional `RUNTIME_DRIFT_MONITOR=1` drift capture.

Monthly: DB checkpoint, evidence prune, Telethon session backup.

## Safe restart

Rolling: stop workers → app → DB maintenance → app → workers.

## Validation

`make soak-test`, `make release-check` on staging after maintenance.

## Rollback

Keep pre-maintenance backup zip.

## Evidence collection

- `soak_harness_report.json`, drift reports, scheduler diagnostics snapshot

## Escalation thresholds

- Memory growth > 40% without traffic increase → investigate leaks
