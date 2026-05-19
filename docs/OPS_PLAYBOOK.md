# Production Operations Playbook Automation

Human-operations enablement for continuous public newsroom operation.

## Enable

```bash
OPS_PLAYBOOK_ENABLED=true
OPS_LAUNCH_PERIOD_DAYS=30
OPS_PRODUCTION_START_AT=2026-05-17T00:00:00+00:00  # optional
```

Inherits `PLATFORM_ENABLED` / `OPS_EVOLUTION_ENABLED` when unset.

## Telegram commands

### Shift handoff
| Command | Action |
|---------|--------|
| `/shift_handoff` | Current handoff report |
| `/take_shift` | Assume shift + persist ownership |
| `/handoff_ack` | Acknowledge warnings |

### War room
| Command | Action |
|---------|--------|
| `/war_room_start <id>` | Incident dashboard, freeze nonessential alerts |
| `/war_room_status [id]` | Timeline + checklist |
| `/war_room_stop [id]` | Close war room |

### Campaign mode
| Command | Action |
|---------|--------|
| `/campaign_mode_start [type]` | breaking / election / sports |
| `/campaign_mode_stop` | Restore normal pacing |
| `/campaign_status` | Active overrides |

### Training (simulation only)
| Command | Action |
|---------|--------|
| `/training_mode` | Enable (use `off` to disable) |
| `/run_drill <scenario>` | Simulated drill — **no live state change** |
| `/drill_results` | Recent scores |

### Reputation
| Command | Action |
|---------|--------|
| `/channel_reputation` | Channel reputation score |
| `/trust_volatility` | Volatility index |

### Executive & audit
| Command | Action |
|---------|--------|
| `/exec_incident_brief <id>` | Mobile executive brief |
| `/ops_audit` | Compliance audit |
| `/compliance_status` | Last audit summary |
| `/launch_period_status` | First-30-days protections |
| `/daily_ops_summary` | On-demand daily rhythm |

## Scheduled rhythms (ops tick)

| Cadence | Content |
|---------|---------|
| Daily | Executive summary, risk, maturity, quality drift, budget |
| Weekly | Optimizations, maintenance, scaling, governance |
| Monthly | Maturity evolution, incident recurrence, sustainability |

## Launch period (first 30 days)

- Elevated anomaly sensitivity
- Stricter rollback/trust thresholds
- Enhanced executive reporting
- Auto-relax after `OPS_LAUNCH_PERIOD_DAYS`

## HTTP

`GET /ops_playbook` — tick snapshot + launch period status

## Daily operator routine

1. `/take_shift`
2. `/shift_handoff` review
3. `/production_ready` + `/platform_health`
4. `/compliance_status`
5. End shift: `/handoff_ack`

## Incident routine

1. `/war_room_start <id>`
2. `/exec_incident_brief <id>`
3. Follow rollback recommendation
4. `/war_room_stop <id>`

## Related

- `docs/PRODUCTION_TELEGRAM_GO_LIVE.md`
- `docs/PRODUCTION_SAFETY_RUNBOOK.md`
