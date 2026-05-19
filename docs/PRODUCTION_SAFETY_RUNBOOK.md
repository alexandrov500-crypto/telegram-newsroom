# Production safety runbook (final hardening)

## Layers

| Layer | Package | Purpose |
|-------|---------|---------|
| Reliability | `bot/reliability/` | Health, recovery, publish gate, incidents |
| Production safety | `bot/production_safety/` | Telegram pacing, budgets, trust, rollout, forensics |

## Rollout stages

1. `INTERNAL_SHADOW` — no public publishes (default)
2. `LIMITED_CHANNELS` — whitelist channels, 6/hour
3. `LOW_FREQUENCY_PUBLIC` — 12/hour
4. `NORMAL_PRODUCTION` — 40/hour
5. `HIGH_VOLUME_PRODUCTION` — 120/hour

```bash
PRODUCTION_ROLLOUT_STAGE=LIMITED_CHANNELS
PRODUCTION_CHANNEL_WHITELIST=-100123,-100456
```

## Emergency controls (Telegram)

| Command | Effect |
|---------|--------|
| `/publish_pause` | Stop all Telegram sends |
| `/publish_resume` | Operator override resume |
| `/rollout_rollback` | Instant INTERNAL_SHADOW + pause |

## Financial modes

| Mode | Trigger |
|------|---------|
| NORMAL | spend &lt; 75% daily cap |
| COST_SAVING | 75–95% cap |
| EMERGENCY_LOW_COST | ≥95% cap — shallow cognition, fallback model hint |

Env: `PRODUCTION_DAILY_BUDGET_USD`, `PRODUCTION_HOURLY_BUDGET_USD`

## Trust states

- **TRUSTED** — may proceed (subject to rollout + reliability gate)
- **REVIEW_REQUIRED** — needs operator approval
- **BLOCKED** — misinfo, duplicate narrative, unsafe content

## Forensics

- `/story_trace <news_id>` — full trace chain
- `/decision_trace <news_id>` — editorial decisions only
- Persisted in `ops_forensics_traces`

## HTTP

- `GET /safety` — production safety snapshot
- `GET /reliability` — reliability snapshot

## Rollback procedure

1. `/rollout_rollback` or set `PRODUCTION_ROLLOUT_STAGE=INTERNAL_SHADOW`
2. Confirm `SHADOW_PUBLISH_ONLY=true`
3. `curl localhost:8080/safety` — `publish_allowed: false`
4. Review `ops_rollout_state.rollback_count` in DB

## Auto-rollback

When `PRODUCTION_AUTO_ROLLBACK_FATAL=true` and a FATAL incident is open, rollout reverts to INTERNAL_SHADOW automatically on the next ops tick.
