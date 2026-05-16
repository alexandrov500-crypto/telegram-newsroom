# Live validation governance

Safe cadence for real Telegram API validation.

## Safe validation cadence

| Activity | Max frequency |
|----------|---------------|
| CI bounded tests | Every PR |
| Staging live session | Weekly max |
| 24h longevity | Quarterly; dedicated account |
| Publish to prod channel | Avoid — use test channel |

## Telegram abuse-prevention boundaries

- No burst > `publish_burst_max_messages` in window intentionally
- No automated loops publishing identical content
- No joining mass channels for stress test
- Collector fetch caps: `raw_fetch_cap`, pipeline interval

## Operator safety rules

1. Test credentials separate from personal account when possible
2. `DRY_RUN` for pipeline validation without send
3. Review `live_telegram_diagnostics.py` before and after
4. Stop on stop conditions ([live_telegram_validation_plan.md](live_telegram_validation_plan.md))

## Live testing limits

- **Hard cap:** 5 publishes per manual session default
- **FloodWait:** abort if wait > 120s once or > 3 waits per hour
- **Media:** 1 media validation per session unless required

## Rollback discipline

- Tag git before live week
- Save diagnostics JSON
- Do not change frozen runtime artifacts as part of live test

## Validation stop conditions

Same as plan: FloodWait loops, duplicates, auth failure, retry storm, operator abort.

## Relation to semantics

Live behavior must match [recovery_semantics.md](../semantics/recovery_semantics.md) and [forbidden_states.md](../semantics/forbidden_states.md).

## Validation commands

```bash
make live-validation-validate
make governance-validate
```

## Non-goals

- Growth hacking / subscriber automation
- Load-test theater without operator checklist
- Mandatory live Telegram in CI (opt-in only)
