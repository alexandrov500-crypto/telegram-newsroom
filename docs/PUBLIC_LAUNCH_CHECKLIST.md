# Public launch checklist

Use this checklist after enabling `FINAL_STAGING_MODE=true` for a 7-day burn-in.

## Environment

- [ ] `PUBLIC_CONTENT_SANITIZER_STRICT=true`
- [ ] `NEWSROOM_TRUST_MODE=high` (or `off` only after burn-in passes)
- [ ] `FINAL_STAGING_MODE=true`
- [ ] `FINAL_STAGING_MAX_PUBLISHES_PER_HOUR=6` (adjust as needed)
- [ ] `SOFT_LAUNCH_MODE=false` unless overlapping soft launch is intentional
- [ ] Single runtime (`active_runtime.json` PID alive, one `app.main`)

## Editorial gates

- [ ] Final publish gate blocks sensational / rumor / governance leaks
- [ ] Tier 3 sources require manual approve (`/approve` + publish)
- [ ] Public channel posts have no debug metadata (sanitizer + output lock)
- [ ] Source attribution: tier 2 footer, tier 3 mandatory, no raw URLs in tier 3 body

## Operations

- [ ] `python3 -m newsroom.cli newsroom` shows pending/failed/latency without raw logs
- [ ] `GET /ops/panel.json` `last_tick.status` = `ok` after one pipeline interval
- [ ] `python3 tools/public_launch_burnin_monitor.py` returns **GO**
- [ ] `python3 tools/final_staging_validator.py --strict` passes on worker host

## Tests

```bash
python3 -m pytest tests/test_public_content_sanitizer.py tests/test_public_post_formatter.py tests/test_trust_mode.py tests/test_staging_mode.py -q
```

## Sign-off

| Role | Date | Notes |
|------|------|-------|
| Operator | | Burn-in monitor GO |
| Editor | | Sample channel posts reviewed |
| Tech | | Staging mode disabled → production profile |

After sign-off: set `FINAL_STAGING_MODE=false`, keep `PUBLIC_CONTENT_SANITIZER_STRICT=true`.
