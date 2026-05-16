# REDIS_RECONNECT_PRESSURE

## Detection

- Redis transport metrics show errors/reconnects
- Workers idle with pending queue depth
- Intermittent publish lock failures

## Mitigation

1. Verify Redis process/memory/network
2. Reduce workers to 1 until stable
3. Review connection pool and timeout settings
4. Restart workers after Redis healthy

## Safe scaling guidance

- Stabilize Redis **before** T2 worker increase
- Do not deploy second node pointing at remote Redis without ops runbook

## Rollback

- Disable multi-worker (`WORKER_COUNT=1`)
- Fall back to T1 single-node if Redis unavailable extended

## Evidence collection

- Redis transport metric snapshots
- Correlation with queue depth timestamps

## Escalation thresholds

| Condition | Action |
|-----------|--------|
| Reconnect loop > 5 min | P1 — T1 fallback |
| Data loss suspected | Stop publish; integrity review |
| Requires Redis Cluster | T4 — unsupported without external program |
