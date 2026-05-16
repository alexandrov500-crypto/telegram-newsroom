# TOKEN_ROTATION

## Detection

- Scheduled rotation interval exceeded
- Suspected leak ([SUSPECTED_SECRET_LEAK.md](SUSPECTED_SECRET_LEAK.md))
- Personnel offboarding

## Containment

1. Revoke old bot token via @BotFather / rotate OpenAI key in dashboard
2. Stop publishers until new `.env` loaded

## Recovery

1. Update `.env` with new secrets
2. Restart app + workers
3. Verify collect/publish smoke in `DRY_RUN` then live

## Evidence preservation

- Export logs **before** rotation (redact if sharing)
- Note timestamps and `correlation_id` values

## Rollback

- Previous tokens cannot be restored if revoked — keep emergency backup token only if provider allows

## Escalation

- Channel compromise → Telegram support / admin audit

## Post-incident validation

- No secrets in recent logs (`SECURITY_REDACTION=1` on new processes)
- `security_posture_check` clean
