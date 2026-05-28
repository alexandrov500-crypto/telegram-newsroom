# Final staging readiness report

**Date:** operator fill-in  
**Environment:** Mac local / VPS Docker  
**Verdict:** NO-GO until operator sign-off below

## Automated checks (repo)

| Check | Command | Expected |
|-------|---------|----------|
| Transport regression | `python3 -m pytest tests/test_telegram_transport.py tests/test_publisher.py tests/test_staging_readiness.py -q` | all pass |
| Singleton | `python3 -m pytest tests/test_runtime_singleton.py -q` | all pass |
| Runtime audit | `python3 tools/runtime_consistency_audit.py` | 0 or 1 `app.main` |
| Single runtime (deployed) | `python3 tools/verify_single_runtime.py --strict` | ok |

## Runtime consistency (P1)

- [ ] `pgrep -fl app.main` — **at most one** line before start
- [ ] VPS `telegram-newsroom` stopped **or** Mac worker stopped (same `BOT_TOKEN`)
- [ ] `NEWSROOM_LOCK_BY_BOT_TOKEN=true`, `RUNTIME_SINGLETON_DISABLED` unset
- [ ] Log line `runtime.code_identity` shows expected `git_sha` + `transport_module` path
- [ ] `curl /health` → `staging.runtime.git_sha` matches deployed commit

## Transport layer (P2)

- [ ] `staging.transport_layer_ok: true`
- [ ] No alert `publishing.legacy_transport_kwargs`
- [ ] Media publish uses `publish.transport_send` (not raw kwargs leak)
- [ ] Optional dry-run: `STAGING_MOCK_TELEGRAM_PUBLISH=true` (mock message ids only)

## Bot responsiveness (P3)

- [ ] Admin `/start` or draft list responds < 5s
- [ ] `staging.bot.polling_active: true`
- [ ] `staging.bot.handler_errors_total` not climbing unbounded

## Publish pipeline (P4)

- [ ] Failed draft: `failed` → retry → `published`
- [ ] `publish.trace` events: started → success
- [ ] `failed_drafts` queue not stuck (terminal after max retries)
- [ ] No duplicate `published_posts` for same `draft_id`

## Observability (P5)

```bash
curl -s http://127.0.0.1:8080/health | python3 -m json.tool | head -120
```

Confirm blocks: `staging.pipeline`, `staging.publishing`, `staging.runtime`, `staging.bot`, `staging.alerts`.

## Success criteria (GO)

1. **3** consecutive pipeline ticks with collect + at least **1** publish (or manual publish) in window  
2. **Zero** `TypeError` / `disable_web_page_preview` in logs and `last_publish_error`  
3. Bot admin commands reliable  
4. `runtime_consistency_audit.py` clean  
5. Checklist [FINAL_STAGING_CHECKLIST.md](runbooks/production/FINAL_STAGING_CHECKLIST.md) signed  

## Operator restart

```bash
bash scripts/runtime_hard_cleanup.sh
bash scripts/start_mac_bot.sh
python3 tools/runtime_consistency_audit.py
python3 tools/final_staging_validator.py
```

## Recover failed drafts (after clean restart)

```bash
python3 tools/recover_publish_draft.py 3 --bypass-cadence
# repeat for drafts 1,2,4 or use admin /publish
```

Expect in `logs/local-run.log`:

- `publish.transport_send` → `kwargs_keys` without `disable_web_page_preview`
- `FORENSIC_MEDIA_SEND` → stack through `telegram_transport.py`
- `publish.success` with `channel_message_id`

## Forensic incident mode

After restart, any legacy `disable_web_page_preview` on media will **crash with RuntimeError** and log:

- `FORENSIC_MEDIA_SEND` — full stack + kwargs_keys
- `FORBIDDEN_MEDIA_KWARGS_DETECTED` — offending keys

Only `publisher/telegram_transport.py` should appear in stacks for channel publish.  
If stack points elsewhere → that path must be removed or routed through transport.

Disable forensic logging (keep fail-closed): `TELEGRAM_MEDIA_FORENSIC=false`

## Sign-off

| Role | GO / NO-GO | Notes |
|------|------------|-------|
| Engineering | | |
| Operator | | |
