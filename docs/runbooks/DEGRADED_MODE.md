# DEGRADED_MODE

## Symptoms

- Operating without Redis, with strict locks off, or with reduced OpenAI/Telegram availability
- Higher duplicate-delivery or manual intervention acceptable temporarily

## Detection

- `REDIS_ENABLED=false` or Redis down with fallback active
- `PUBLISH_LOCK_STRICT=0` and `publish_lock_redis_fallback` > 0
- `DRY_RUN=true` or `NEWSROOM_SAFE_MODE=true`

## Immediate Mitigation

1. **Declare degraded** in operator log (timestamp, config snapshot).
2. Limit to **single process** for publish + pipeline where possible.
3. Increase inspection frequency: `scripts/runtime_sanity_check.sh`.

## Safe Recovery

1. Restore dependencies in order: DB stable → Redis → external APIs.
2. Enable `PUBLISH_LOCK_STRICT=1` before scaling workers > 1.
3. Enable `WORKER_RETRY_SAFE=1` when running multiple workers with Redis queue.

## Validation Steps

```bash
OUTPUT_DIR=./runtime_ops_output STRICT=0 ./scripts/runtime_sanity_check.sh
make verify-runtime OUTPUT_DIR="$OUTPUT_DIR"
```

## Rollback Strategy

Return to known-good `.env` from version control; avoid mixing degraded and production flags without restart.

## Evidence Collection

- Env dump (redact secrets): `REDIS_ENABLED`, `PUBLISH_LOCK_STRICT`, `WORKER_RETRY_SAFE`
- Nightly `OUTPUT_DIR` bundle after recovery
- [BURN_IN_REPORT.md](../BURN_IN_REPORT.md) checklist rows

## Escalation Notes

Degraded mode is **not** an HA story — no SLA. See [KNOWN_LIMITATIONS.md](../KNOWN_LIMITATIONS.md).
