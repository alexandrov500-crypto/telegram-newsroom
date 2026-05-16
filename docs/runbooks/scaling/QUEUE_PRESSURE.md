# QUEUE_PRESSURE

## Detection

- Pending + processing depth sustained high per job kind
- `oldest_pending_age_sec` growing in queue diagnostics
- Nightly artifacts show backlog warnings

```bash
python3 tools/scalability_diagnostics.py --output-dir "$OUTPUT_DIR"
```

## Mitigation

1. Pause non-essential enqueue sources
2. Verify workers running and Redis healthy
3. Fix upstream API failures (OpenAI/Telegram)
4. Recover stale processing jobs per worker visibility settings

## Safe scaling guidance

- Add **one** worker only if retry burst below storm threshold and Redis stable
- Do not exceed CPU-core heuristic ([multi_worker_discipline.md](../../scalability/multi_worker_discipline.md))
- Enable `WORKER_RETRY_SAFE=1` and `PUBLISH_LOCK_STRICT=1` before T2 scale-out

## Rollback

- Scale workers back to previous count
- Drain queue intentionally if poison messages suspected (DLQ path)

## Evidence collection

- Save scalability diagnostics JSON
- Export queue diagnostic samples from nightly `OUTPUT_DIR`
- Note timestamps of depth peaks

## Escalation thresholds

| Condition | Action |
|-----------|--------|
| Depth > 200 > 30 min | Stop scaling; incident review |
| Depth rising with zero processing | Redis/worker outage — P1 |
| Repeated after upstream fix | Architecture review (not more workers) |
