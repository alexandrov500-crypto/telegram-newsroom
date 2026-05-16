# REDIS_DOWN

## Symptoms

- Workers log `redis` / `ConnectionError` / transport reconnect loops
- `PUBLISH_LOCK_STRICT=1` publishes deferred (`publish_lock.strict_denied`)
- Queue depth metrics stale; DLQ pages empty or error in `/ops/dlq`

## Detection

- `redis-cli -u "$REDIS_URL" PING` fails
- `publish_lock_strict_denied` or `publish_lock_redis_fallback` counters increase
- Worker heartbeat shows transport errors

## Immediate Mitigation

1. **Single-worker mode:** set `REDIS_ENABLED=false` only if exactly one app + one worker set (see [DEGRADED_MODE.md](DEGRADED_MODE.md)).
2. **Multi-worker:** do **not** disable strict lock; stop extra publishers/workers until Redis returns.
3. Restart Redis service or fix network ACLs.

## Safe Recovery

1. Restore Redis; verify `PING`.
2. Restart workers one at a time (avoid duplicate publish window).
3. Enable `PUBLISH_LOCK_STRICT=1` when more than one publisher process may run.

## Validation Steps

```bash
make runtime-index OUTPUT_DIR="$OUTPUT_DIR"
python3 -m newsroom.cli verify-runtime --path "$OUTPUT_DIR"
```

Re-run a single test job; confirm no `strict_denied` in logs.

## Rollback Strategy

Revert env to pre-incident `REDIS_URL` / `REDIS_ENABLED`. If duplicate publishes suspected, inspect channel for duplicate message ids and draft `published` state in DB.

## Evidence Collection

- Redis logs, `utils/redis_transport_metrics` snapshot (if exported)
- `lock_events` via diagnostics buffer or metrics counters
- Worker DLQ samples: `/ops/dlq` or `tools/admin_cli.py`

## Escalation Notes

Persistent split-brain duplicate publishes require manual channel cleanup — not auto-healed by inspection CLIs.
