# Controlled Public Pilot

Final pre-production phase: limited live exposure with continuous observation.

## Required env (first 48 hours)

```bash
CONTROLLED_LIVE_ENABLED=true
LIVE_MODE=canary
LIVE_CANARY_MAX_PER_HOUR=3
LIVE_SUPERVISED_APPROVAL=true
LIVE_FREEZE_ON_ANOMALY=true
LIVE_ENABLE_ROLLBACK=true
LIVE_ALLOWED_SOURCES=reuters,ap,bloomberg
```

## Channel setup

| Channel | Env | Purpose |
|---------|-----|---------|
| Public test | `LIVE_PUBLIC_CHANNEL_ID` or `TELEGRAM_CHANNEL_ID` | Real posts, engagement telemetry |
| Internal ops | `LIVE_OPS_CHANNEL_ID` or `TELEGRAM_OPERATOR_CHAT_ID` | Holds, freeze, rollback, anomalies |
| Shadow (optional) | `LIVE_SHADOW_CHANNEL_ID` or `TELEGRAM_DIGEST_CHANNEL_ID` | Shadow vs live comparison |

Public channel should be small, with an experimental disclaimer acceptable.

## New capabilities

### Publish decision trace (`publish_trace.py`)

Every publish decision persisted in `live_publish_trace`:

- `/publish_trace <pending_news_id>`
- `GET /publish_trace/{pending_news_id}`

### Source quarantine (`source_quarantine.py`)

3 bad posts from same source in 24h → 6h cooldown (configurable):

- Source routes to shadow or block
- `/source_quarantine` status
- Triggered by `/mark_bad_post <id> <source>`

### Metrics snapshot (every 5 min)

Stored in `live_metrics_snapshots`:

- `GET /live_metrics_timeline`

### Startup validation

On startup: DB, tables, Telegram config, live mode (blocks `autonomous_live` during pilot), rollback repo, OpenAI key, event bus.

Critical failure → forced `SHADOW` + ops alert. No live publish on degraded startup.

## Pilot rules

**First 48h:** `LIVE_MODE=canary` only — no `autonomous_live`.

**Human review:** Use `/mark_good_post` and `/mark_bad_post` on every sampled live post.

**Emergency commands** (work in degraded mode):

- `/freeze_publishing`
- `/resume_live`
- `/rollback_last_batch`
- `/live_status`
- `/live_dashboard`

## Success criteria

- 7 consecutive stable days
- No catastrophic publishes
- Rollback and freeze verified
- Operator can explain any publish via trace

## After pilot

1. `LIVE_MODE=supervised_live`
2. Adaptive canary + reputation decay
3. Only then `autonomous_live`

## Tests

```bash
python3 -m pytest tests/test_controlled_live.py tests/test_controlled_pilot.py -q
```
