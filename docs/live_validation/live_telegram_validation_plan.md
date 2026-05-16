# Live Telegram validation plan

Controlled real-world validation — **not** mass rollout or load testing.

## Validation scope

| In scope | Out of scope |
|----------|--------------|
| Telethon session connect/reconnect | Multi-region deploy |
| aiogram publish pacing + chunks | Spam / flood publishing |
| FloodWait handling (collector) | Public channel load tests |
| Publish lock + rate limiter | K8s migration |
| Worker retry semantics (live env) | Autonomous remediation |
| Operator moderation/DLQ flows (manual checklist) | Contract/schema changes |

## Safe publish limits

- Use **test channel** or low-traffic target only (`TARGET_CHANNEL_ID`).
- Respect `publish_channel_min_interval_sec` and burst settings (production profile ≥ defaults).
- Max **3–5** publishes per validation session unless operator approves more.
- Enable `DRY_RUN=1` for pipeline-only passes without send.
- Inter-chunk delay per `telegram_inter_chunk_delay_sec` — do not zero in live runs.

## Allowed Telegram workloads

- Single-node T1 or bounded T2 (Redis + strict flags).
- Editorial cadence simulation (minutes between publishes, not seconds).
- Collector fetch on limited source channels.
- Admin bot moderation actions by operator only.

## Operator safety constraints

- Credentials only via env — never commit sessions.
- `SECURITY_REDACTION=1` recommended for shared logs.
- Stop if FloodWait > 60s repeatedly or account restrictions suspected.
- No scripted mass channel joins or forwards.

## Validation duration

| Tier | Duration | Mode |
|------|----------|------|
| CI bounded | < 2 min | Mocks + harness |
| Staging live | 1–4 hours | `TELEGRAM_LIVE_VALIDATE=1` |
| Long-running | 24h+ | Manual opt-in; external supervisor |

## Rollback expectations

- Revert `.env` flag changes.
- `reset_failed_draft_to_pending` per runbook for stuck drafts.
- Redis flush only with operator approval (queue loss).
- Git tag before live session recommended.

## Stop conditions

1. Account FloodWait loop or ban risk signals
2. Duplicate publishes detected on channel
3. Session auth failures (`SessionPasswordNeededError`)
4. `retry_burst_window` at storm threshold sustained
5. Operator abort

## Execution

```bash
# CI-safe bounded suite
make live-validation-test

# Read-only diagnostics (no Telegram calls)
python3 tools/live_telegram_diagnostics.py

# Opt-in live (credentials required)
TELEGRAM_LIVE_VALIDATE=1 pytest tests/live -m live_telegram -v
```
