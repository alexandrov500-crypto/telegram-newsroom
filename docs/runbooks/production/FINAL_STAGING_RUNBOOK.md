# Final staging runbook

## Smoke: end-to-end dry path

1. Stop duplicate runtimes:
   ```bash
   bash scripts/stop_local_newsroom.sh
   # On VPS if Mac is active: stop telegram-newsroom service
   ```
2. Start worker:
   ```bash
   bash scripts/start_mac_bot.sh
   # or deploy-safe on VPS
   ```
3. Wait for pipeline tick (`scheduler.pipeline_tick` phase=end in logs).
4. Inspect health:
   ```bash
   curl -s http://127.0.0.1:8080/health | python3 -m json.tool | head -80
   ```
5. If `drafts_pending > 0`, approve/publish via admin bot or CLI.
6. Confirm DB:
   ```bash
   sqlite3 data/newsroom.db "SELECT id, status, last_publish_error FROM drafts ORDER BY id DESC LIMIT 5;"
   sqlite3 data/newsroom.db "SELECT * FROM published_posts ORDER BY id DESC LIMIT 3;"
   ```

## Publish retry inspection

```bash
sqlite3 data/newsroom.db "SELECT draft_id, retry_count, status, last_error, next_retry_at FROM failed_drafts;"
```

Terminal state: `status=terminal` with `terminal_failure_reason` (dead-letter).

## Desk replay (tuning validation)

```python
from app.editorial.replay_simulation import replay_rejected_items
print(replay_rejected_items("var/runtime", limit=30))
```

Compare `flip_to_publish` / `flip_to_reject` before changing `DESK_CATEGORY_*` env vars.

## Critical alerts

| Code | Meaning | Action |
|------|---------|--------|
| `pipeline.collect_without_drafts` | Ingest works, no drafts N ticks | Check desk/governance/OpenAI; see PIPELINE_STALL runbook |
| `publishing.degraded` | Many failures in 1h | Inspect `failed_drafts`, Telegram errors |
| `openai.generation_degraded` | Circuit open | OPENAI_DEGRADED runbook |
| `editorial.starvation_recovery_active` | Recovery on, no publishes | Verify thresholds; manual publish one quality draft |

## Emergency halt

Set `OPS_EMERGENCY_HALT=true` (or ops control plane). Verify publish blocked in logs (`publish.blocked_operational_mode`).

## Restart safety

After restart: one `app.main` PID, `pipeline_ticks` advancing, no duplicate `published_posts` for same `draft_id`.
