# First 72 Hours — Live Public Operations

Operator runbook for the **first real public deployment** window.

## Launch sequence (exact)

```bash
cp deploy/production/env.production.example .env.production
# Fill secrets: TELEGRAM_BOT_TOKEN, channel IDs, ADMIN_USER_IDS, OPENAI_API_KEY, DATABASE_URL, REDIS_URL

export FIRST_72H_MODE=true
export LIVE_DEPLOY_ENABLED=true
export SHADOW_PUBLISH_ONLY=true
export PRODUCTION_ROLLOUT_STAGE=INTERNAL_SHADOW

chmod +x scripts/*.sh
bash scripts/live_production_start.sh
```

Success ends with: **`GO-LIVE READY`**

## Continuous monitoring

```bash
bash scripts/live_watch.sh
```

## Shift procedures

| When | Command |
|------|---------|
| Start shift | `/take_shift` |
| Review state | `/shift_handoff` |
| End shift | `/handoff_ack` |

## First publication checklist

1. `/production_ready` → no blockers  
2. `/go_live_certify` → CERTIFIED  
3. `/channel_status` → all permissions ✓  
4. `/first_publication_status` → gates green  
5. `/advance_publication` → FIRST_REAL_PUBLICATION  
6. Set `SHADOW_PUBLISH_ONLY=false` only after operator sign-off  
7. Approve **one** item manually in operator console  
8. Confirm publish in channel; run `/channel_reputation`  

## Escalation matrix

| Severity | Symptom | Action |
|----------|---------|--------|
| P0 | Public publish failure storm | `bash scripts/emergency_rollback.sh` |
| P0 | FloodWait / Telegram ban risk | `emergency_shadow_mode.sh` + lower publish rate |
| P1 | OpenAI outage | `emergency_shadow_mode.sh` |
| P1 | Quality collapse | `/rollout_rollback` + `/war_room_start` |
| P2 | Queue backlog | Throttle ingest; `/campaign_mode_stop` |
| P2 | Operator overload | `/handoff_ack` + second operator `/take_shift` |

## Rollback triggers (first 72h — stricter)

| Metric | Threshold | Action |
|--------|-----------|--------|
| Publish failure rate | > 3% (15m) | `emergency_shadow_mode.sh` |
| GA confidence | < 0.75 | Hold ramp |
| Trust volatility | > 0.12 | `/channel_reputation` review |
| SLO burn | > 0.10 | `emergency_rollback.sh` |
| Poison queue growth | monotonic 30m | Stop workers, rollback |

## Incident workflow

```
/war_room_start <incident_id>
/exec_incident_brief <incident_id>
/emergency_rollback.sh (if needed)
/war_room_stop <incident_id>
```

## Campaign workflow (breaking news)

```
/campaign_mode_start breaking
/campaign_status
# ... event ...
/campaign_mode_stop
```

## Emergency scripts

| Script | Effect |
|--------|--------|
| `scripts/emergency_freeze.sh` | Governance freeze, no auto-approval |
| `scripts/emergency_shadow_mode.sh` | Shadow-only publishes |
| `scripts/emergency_rollback.sh` | Shadow + worker stop + rollout rollback |
| `scripts/recovery_resume.sh` | Restart infra, remain shadow |

All scripts append to `var/log/emergency_audit.log`.

## Telegram failure

1. `python3 scripts/telegram_live_validation.py`  
2. Re-add bot as channel admin (all five rights)  
3. `bash scripts/recovery_resume.sh`  

## OpenAI degradation

1. `emergency_shadow_mode.sh`  
2. Lower `GA_MAX_PUBLISHES_PER_HOUR`  
3. Monitor `/reliability` and budget metrics  

## Executive reports (automatic)

| Milestone | Report key |
|-----------|------------|
| Startup | `startup` |
| First hour | `first_hour` |
| 24h | `24h` |
| 72h | `72h` |

Manual: `python3 -m bot.live_deploy.cli send-startup-report`

## Training (never touches production)

```
/training_mode
/run_drill rollback_rehearsal
/drill_results
```

Production drills: `python3 -m bot.live_deploy.cli drill rollback_rehearsal`

## Commands reference

`/startup_check` `/production_ready` `/first_72h_status` `/live_deploy_status`  
`/ops_audit` `/compliance_status` `/platform_health` `/shift_handoff`

## Related

- `docs/PRODUCTION_TELEGRAM_GO_LIVE.md`
- `docs/OPS_PLAYBOOK.md`
