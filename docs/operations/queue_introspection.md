# Queue introspection (read-only)

`tools/queue_introspection.py` — visibility into job queues, DLQ depth, publish-lock TTL, and retry amplification **without** dequeue, retry, or lock mutation.

## Usage

```bash
python3 tools/queue_introspection.py
python3 tools/queue_introspection.py --json-output /tmp/queue.json
```

## Output fields

| Section | Meaning |
|---------|---------|
| `transport_mode` | `redis` or `memory` |
| `queues.<kind>.pending_count` | Jobs waiting (Redis LLEN) |
| `queues.<kind>.processing_count` | In-flight lease list |
| `queues.<kind>.dlq_count` | DLQ depth |
| `queues.<kind>.oldest_pending_age_sec` | From `_enqueue_wall_ts` on list tail |
| `publish_locks[]` | SCAN `*:publish_lock:*` with TTL |
| `retry_amplification` | `retry_burst_window`, counters, trace sample count |

## Safety

- **No** `LPOP`, `BRPOP`, `DEL`, `SET`, or replay
- Safe when Redis unavailable — reports `memory` / errors per queue
- Does not initialize workers unless queue already up

## Operator interpretation

| Signal | Action |
|--------|--------|
| High `dlq_count` | Manual DLQ review per runbook |
| High `oldest_pending_age_sec` | Check worker health |
| Many `publish_locks` with low TTL | Possible contention — see diagnostics |
| `retry_burst_window` high | [RETRY_STORM_RECOVERY.md](../runbooks/RETRY_STORM_RECOVERY.md) |

## Related

- ADR-030
- [operator_shift_checklist.md](../runbooks/operator_shift_checklist.md)
