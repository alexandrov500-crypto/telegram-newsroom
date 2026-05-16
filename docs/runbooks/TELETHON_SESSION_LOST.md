# TELETHON_SESSION_LOST

## Symptoms

- Collector cannot fetch source channels
- `telethon` auth errors, session invalid, or missing session file
- `posts_collected` flatlines

## Detection

- Logs from `collector/telethon_client.py`
- Session path empty or file removed (not in `backup_cli` zip by default)
- `TELETHON_SESSION_STRING` / `TELETHON_SESSION_PATH` mis-set after deploy

## Immediate Mitigation

1. Pause pipeline collection (stop scheduler tick or `DRY_RUN` if acceptable).
2. Do not delete session file until re-auth plan confirmed.

## Safe Recovery

1. Re-authenticate Telethon per [QUICKSTART.md](../QUICKSTART.md) on trusted host.
2. Update `.env` with new `TELETHON_SESSION_STRING` or session file path.
3. Verify collect with bounded manual run.

## Validation Steps

- Collector smoke: single channel fetch count > 0
- Metrics `posts_collected` increases on next tick

## Rollback Strategy

Restore previous session file from secure offline backup if available.

## Evidence Collection

- Session path (redact secrets in tickets)
- Collector error stack traces
- Deploy change log (env rotation dates)

## Escalation Notes

Include Telethon session in operator DR checklist — not automated in v1.0.x backup zip.
