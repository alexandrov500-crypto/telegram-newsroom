# Controlled Live Channel Testing

Safe transition from production-ready architecture to daily operation with a real Telegram audience.

## Purpose

Controlled real-world validation — not scaling, not new AI features. Operator trust, rollback safety, and observability first.

## Live modes (`LIVE_MODE`)

| Mode | Behavior |
|------|----------|
| `shadow` | Internal/shadow channel only |
| `canary` | Rate-limited public posts, whitelist optional |
| `supervised_live` | Live publishing + mandatory operator monitoring |
| `autonomous_live` | Full live (only after stabilization sign-off) |

## Enable

```bash
CONTROLLED_LIVE_ENABLED=true
LIVE_MODE=supervised_live
LIVE_CANARY_MAX_PER_HOUR=6
LIVE_SUPERVISED_APPROVAL=true
```

## Safety layers

1. **LiveChannelPublishGuard** — content heuristics (empty/short summary, broken markdown, phrase loops)
2. **CanaryPublisher** — hourly cap, source/topic whitelist, safe hours
3. **IncidentFreeze** — auto-pause after failure threshold + cooldown
4. **AnomalyHold** — freeze on consecutive failure spike
5. **RollbackControl** — batch rollback → shadow + pause
6. **OperatorOverride** — pause/resume/freeze/mark good|bad

Integrates in `publish_flow.py` after `live_deploy` guard.

## Operator commands

| Command | Action |
|---------|--------|
| `/live_status` | Mode, pause, trust, success rate |
| `/canary_status` | Hourly cap, safe hours |
| `/pause_live` / `/resume_live` | Stop/start publishing |
| `/freeze_publishing` | Hard freeze |
| `/rollback_last_batch` | Shadow + pause + incident |
| `/review_recent_posts` | Publish audit log |
| `/mark_bad_post` / `/mark_good_post` | Operational labeling |
| `/live_incidents` | Recent incidents |
| `/channel_health` | Queue + survivability context |
| `/live_dashboard` | Summary dashboard |

## HTTP

- `GET /live_status`
- `GET /channel_health`
- `GET /recent_incidents`
- `GET /live_feedback`
- `GET /publishing_safety`

## Rollout checklist

1. [ ] `LIVE_MODE=shadow` for 24–48h — validate formatting, media, multilingual
2. [ ] Review `/review_recent_posts` and shadow channel quality
3. [ ] `LIVE_MODE=canary` with `LIVE_CANARY_MAX_PER_HOUR=3` and source whitelist
4. [ ] Operator marks posts good/bad — trust score stabilizes
5. [ ] `LIVE_MODE=supervised_live` with approval required
6. [ ] Run `scripts/telegram_live_validation.py` if available
7. [ ] Only after 7+ stable days: consider `autonomous_live`

## Failure modes

| Risk | Mitigation |
|------|------------|
| Runaway publishing | Canary hourly cap + pause/freeze |
| Bad summary live | Content heuristics + hold + operator alert |
| Telegram FloodWait | Existing reliability layer + pause |
| False freeze | `/resume_live` + check `failures_recent` |
| Duplicate with live_deploy | live_deploy = quality/trust; controlled_live = mode/canary/content |

## Emergency

```bash
bash scripts/emergency_shadow_mode.sh
# or in Telegram:
/freeze_publishing
/rollback_last_batch
```

## Tests

```bash
python3 -m pytest tests/test_controlled_live.py -q
```
