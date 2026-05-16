# PARTIAL_PUBLISH

## Symptoms

- Channel shows truncated multi-part post (only first chunks)
- Draft marked `published` but content incomplete
- `telegram_api_failures` or `publish_failures` counters increased

## Detection

- Logs: `telegram_publisher` chunk N failed after earlier chunks succeeded
- Admin reports mismatch between draft preview and channel text

## Immediate Mitigation

1. Enable `DRY_RUN=true` to stop new publishes while investigating.
2. Post manual correction to channel if editorial policy requires.
3. Mark draft state: consider `failed` + reset via admin workflow (operator judgment).

## Safe Recovery

1. Review `publisher/telegram_publisher.py` chunk boundaries and `MAX_POST_CHARS`.
2. Re-publish only after fixing root cause (token, flood wait, content size).
3. Use idempotency key if re-attempting same draft.

## Validation Steps

- Dry-run publish path for same draft id
- Single-chunk test message to target channel (operator account)

## Rollback Strategy

Delete erroneous channel messages manually (Telegram UI); revert draft DB status from backup if corrupted.

## Evidence Collection

- Draft id, channel message ids, publish logs
- Metrics: `telegram_api_failures`, `publish_failures`
- Timeline events in operational dashboard bundle

## Escalation Notes

Multi-chunk publish is not atomic in v1.0.x — treat as known unsafe scenario under network loss.
