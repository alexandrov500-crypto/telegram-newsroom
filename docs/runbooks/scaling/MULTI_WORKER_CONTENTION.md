# MULTI_WORKER_CONTENTION

## Detection

- Publish lock wait spikes; duplicate publish attempts in logs
- `multi_worker_contention_risk` in scalability diagnostics
- Queue depth ok but publish errors elevated

## Mitigation

1. Set `PUBLISH_LOCK_STRICT=1`
2. Reduce workers to 1 until lock/redis stable
3. Verify single SQLite writer

## Safe scaling guidance

- T2 requires Redis + strict lock + retry safe
- Add workers one at a time; observe lock metrics

## Rollback

- `WORKER_COUNT=1`
- Disable strict only after deliberate risk acceptance (documented)

## Evidence collection

- Lock event traces from reliability diagnostics
- Worker count and flag snapshot

## Escalation thresholds

| Condition | Action |
|-----------|--------|
| Duplicate publishes confirmed | P0 contain + audit |
| Lock unavailable with multi-worker | Fail-closed expected — fix Redis |
| Contention at 2 workers | Do not scale to 4 |
