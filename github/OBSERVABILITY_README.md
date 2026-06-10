# ADR-037 Live Observability Layer

**STATUS: CLOSED** — architecture frozen. See [docs/adr037-final-operational-form.md](../docs/adr037-final-operational-form.md).

Runtime operational control plane for migration M0→M3. **Observe and alert only** — no auto rollback, no phase advancement.

## Components

| Script | Role |
|--------|------|
| `scripts/migration_event_stream.py` | Aggregate gate/risk/rollback/incident events |
| `scripts/event_rules_engine.py` | Rules → incidents + dashboard + optional notify |
| `scripts/telegram_incident_bot.py` | Primary operator channel (Telegram) |
| `scripts/slack_migration_mirror.py` | Secondary mirror (NO-GO, CRITICAL, rollback) |

## Environment

```bash
export TELEGRAM_BOT_TOKEN=...
export INCIDENT_CHAT_ID=...          # operator group / user id
export SLACK_MIGRATION_WEBHOOK_URL=...  # optional
```

## Operator commands (Telegram)

- `/status` — phase + last gate decision
- `/gate` — last evaluation summary
- `/risk` — active HIGH/CRITICAL risks
- `/rollback` — rollback proposals (proposal-only)
- `/ack <incident_id>` — acknowledge incident

## Local run

```bash
pip install pyyaml aiogram

python scripts/migration_event_stream.py --persist
python scripts/event_rules_engine.py
python scripts/telegram_incident_bot.py --poll   # long-running bot
```

## Event rules

1. **3× NO-GO** in recent window → incident `systemic_gate_failure`
2. **CRITICAL risk** active → incident + Telegram/Slack alert
3. **Same gate fails 2×** → escalation alert
4. **Rollback proposal** → operator notification

## Source files (GitHub truth)

- `github/migration_state.txt` — human-owned phase
- `github/gate_evaluation_history.jsonl` — gate automation output
- `github/risk_registry.yaml` — risk registry
- `github/incidents_store.yaml` — structured incidents
- `github/gate_status_snapshot.md` — live dashboard (auto-updated)
