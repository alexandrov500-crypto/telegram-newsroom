# REDIS_RECONNECT_STORM

## Detection

- Transport reconnect logs looping
- `publish_lock_redis_fallback` increasing

## Mitigation

1. Stabilize Redis/network.
2. `PUBLISH_LOCK_STRICT=1` when multi-worker.
3. Reduce worker count until Redis healthy.

## Safe restart

Restart Redis, then workers, then app.

## Validation

`redis-cli PING`; publish test in `DRY_RUN`.

## Rollback

Disable Redis only for single-node emergency ([DEGRADED_MODE.md](DEGRADED_MODE.md)).

## Evidence collection

- Redis logs, transport metrics, lock event buffer

## Escalation thresholds

- >100 reconnects/hour → infrastructure incident
