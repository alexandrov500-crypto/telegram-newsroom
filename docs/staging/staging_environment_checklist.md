# Staging environment checklist

Pre-flight for controlled v3 live validation and production-lite rollout. **Staging/test channel only** — never production audience channels.

## Env matrix

| Variable | Required | Staging expectation | Verify |
|----------|----------|---------------------|--------|
| `TELEGRAM_API_ID` | Yes | my.telegram.org app id | `staging_environment_verify.py` |
| `TELEGRAM_API_HASH` | Yes | 32-char hash | masked check only |
| `TELETHON_SESSION_STRING` **or** `TELETHON_SESSION_PATH` | Yes | Valid session; not placeholder | connect test |
| `BOT_TOKEN` | Yes (publish path) | @BotFather staging bot | bot getMe smoke |
| `ADMIN_USER_ID` | Yes | Operator Telegram user id | admin command auth |
| `TARGET_CHANNEL_ID` | Yes | **Private staging channel** | negative id; not prod |
| `SOURCE_CHANNELS` | Yes | Low-traffic test sources | comma list parse |
| `DATABASE_URL` | Yes | `sqlite+aiosqlite:///...` writable | file exists |
| `RUNTIME_STATE_DIR` | Yes | `var/runtime` writable | mkdir ok |
| `DRY_RUN` | Phase T0 | `true` first | no channel send |
| `REDIS_ENABLED` | T2 only | `false` T0/T1; `true` T2 | PING if enabled |
| `PUBLISH_LOCK_STRICT` | T2 | `false` T1; `true` with Redis | paired with Redis |
| `TELEGRAM_LIVE_VALIDATE` | Live tests only | `1` during sign-off window | opt-in marker |

Reference templates: `.env.example`, `deploy/example.env.production-lite`.

## Required secrets (never commit)

- Telethon session (string or SQLite file on volume)
- Bot token
- OpenAI key (pipeline only; not required for connect-only live test)

Store in `.env` on staging host only. Rotate per `docs/runbooks/security/TOKEN_ROTATION.md`.

## Startup expectations

| Component | Command / check | Healthy signal |
|-----------|-----------------|----------------|
| Config | `python3 tools/staging_environment_verify.py` | `status: OK` or documented WARNING |
| Diagnostics | `make live-telegram-diagnostics` | `read_only: true`, schema v2 |
| Scheduler | `python3 -m scheduler` or compose service | tick logs without traceback |
| Worker | `python3 -m workers` (profile-specific) | consumer connected / idle |
| DRY_RUN publish | Admin publish on test draft | `publish.dry_run_skipped` in logs |
| Bounded live | `TELEGRAM_LIVE_VALIDATE=1 pytest tests/live -m live_telegram -v` | connect/disconnect pass |

## Safe test limits (governance)

| Limit | Value |
|-------|-------|
| Max publish operations per session | **5** |
| Target | Staging channel id only |
| Concurrent publishers | 1 (T1) |
| Load / spam | **Forbidden** |
| Runtime JSON schema | **No changes** |

## Rollback conditions

Stop staging validation and revert flags if any:

1. Duplicate message on staging channel
2. Sustained FloodWait loop or account restriction signal
3. `live_telegram_diagnostics` status `FAIL` (HIGH findings)
4. `FINALIZE_MISMATCH` or unexplained `publishing` stuck state
5. Redis strict lock denied under expected-available Redis
6. Operator abort

Rollback actions:

- Set `DRY_RUN=true`; stop scheduler/worker
- Revert `.env` to last known-good
- `reset_failed_draft_to_pending` per runbook for stuck drafts
- Do not flush Redis without operator approval

## Verification commands

```bash
python3 tools/staging_environment_verify.py
make live-telegram-diagnostics
make live-validation-validate
# After .env configured:
TELEGRAM_LIVE_VALIDATE=1 pytest tests/live -m live_telegram -v
```

## Sign-off linkage

- Live results: [live_staging_signoff.md](live_staging_signoff.md)
- Failure injection: [failure_injection_results.md](failure_injection_results.md)
- Rollout: [../operations/production_lite_rollout.md](../operations/production_lite_rollout.md)
