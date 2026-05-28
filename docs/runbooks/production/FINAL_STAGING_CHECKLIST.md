# Final staging checklist (pre-public channel launch)

Complete in order on the **single active worker** (VPS *or* Mac — never both with the same `BOT_TOKEN`).

## Environment & credentials

- [ ] `OPENAI_API_KEY` valid; billing/quota verified (`curl /health` → `openai` not degraded)
- [ ] `BOT_TOKEN` matches the intended runtime (VPS worker **or** local Mac, not both)
- [ ] `CHANNEL_ID` / publish target is the **staging or production** channel (not a test DM)
- [ ] `DATABASE_URL` points to the intended SQLite file; backup taken
- [ ] `.env` matches `deploy/timeweb/.env.example` / root `.env.example` for new staging keys

## Telegram permissions

- [ ] Bot is admin on target channel (post messages, edit, delete if used)
- [ ] Bot can send **photo** and **video** (test with draft that has media)
- [ ] Admin bot responds to operator (`/health`, draft list, approve/publish)
- [ ] No `409 Conflict` in logs (only one poller per token)

## Pipeline & editorial

- [ ] `curl -s http://127.0.0.1:8080/health | jq .staging` shows recent ticks
- [ ] Collect produces rows (`posts_collected > 0` on recent tick)
- [ ] Desk approve/reject logged as `desk.decision` with `reason_code`
- [ ] Governance/suppression **not** globally disabled
- [ ] Starvation recovery only when `staging.editorial.publish_starvation_detected` or desk hint says so
- [ ] Hard rejects still block meme/clickbait/marketing patterns

## Publishing

- [ ] Text-only draft publishes (`published_posts` row + `publish.trace` success)
- [ ] Photo draft publishes (no `disable_web_page_preview` on media send)
- [ ] Video draft publishes
- [ ] Long post splits without HTML parse errors
- [ ] Retry: force transient failure → `failed_drafts` → backoff → success or terminal
- [ ] Duplicate publish blocked (idempotency / journal replay)
- [ ] `publish.trace` includes `draft_id`, `publish_attempt`, `telegram_message_id`, `latency_ms`

## Operations & safety

- [ ] `OPS_EMERGENCY_HALT=true` stops new publishes (verify, then disable)
- [ ] Graceful stop: `scripts/stop_local_newsroom.sh` — no duplicate scheduler after restart
- [ ] `NEWSROOM_LOCK_BY_BOT_TOKEN=true` prevents second local process
- [ ] Structured JSON logs only for operator dashboard queries
- [ ] Critical alert **not** firing: `pipeline.collect_without_drafts` (see `/health` → `staging.alerts`)

## Regression tests

```bash
cd "/Users/markusgronholm/telegram newsroom"
pytest tests/test_final_staging.py tests/test_publisher.py tests/test_desk_starvation.py -q
```

## Sign-off

| Role | Name | Date | GO / NO-GO |
|------|------|------|------------|
| Operator | | | |
| Engineering | | | |
