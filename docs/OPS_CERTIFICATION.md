# Operations Certification & Chaos Hardening

Final go-live execution layer: SLOs, formal certification, controlled chaos, governance, and executive reporting.

## Package layout

```
bot/ops_certification/
  chaos/          # Controlled failure injection
  slo/            # SLO windows, burn rate, error budget
  certification/  # NOT_READY → CERTIFIED states
  security/       # Immutable audit chain
  incidents/      # Review, timeline, postmortem drafts
  longevity/      # Month-long aging protections
  governance/     # Editorial freeze, quarantine, consensus
  mesh/           # Multi-node health aggregation
  reporting/      # Executive daily summaries
  command_center/ # Telegram operator commands
```

## Operator commands

| Command | Purpose |
|---------|---------|
| `/chaos_status` | Active drills + recent runs |
| `/chaos_run <scenario>` | Run controlled chaos drill |
| `/slo_live` | Rolling SLO compliance |
| `/error_budget` | Burn rate summary |
| `/certification_status` | Formal certification checks |
| `/go_live_certify` | Persist certification evaluation |
| `/security_status` | Audit + admin activity |
| `/audit_trace <id>` | Verify hash chain entry |
| `/incident_review <id>` | Timeline + rollback hints |
| `/freeze_editorial` | Pause ingestion (use `off` to unfreeze) |
| `/governance_status` | Freeze, quarantine, consensus |
| `/exec_report` | Daily executive summary |

HTTP: `GET /certification` on health port.

## Chaos scenarios

- `redis_outage`, `telegram_timeout`, `openai_latency`, `worker_crash`
- `queue_corruption`, `cognition_delay`, `replay_corruption`, `network_partition`

Enable with `OPS_CHAOS_ENABLED=true`. Scheduled safe drills: `OPS_CHAOS_SCHEDULED=true`.

Safety: drills abort below survivability threshold; auto-rollback hooks production safety shadow stage.

## Certification states

| State | Meaning |
|-------|---------|
| `NOT_READY` | Blockers present — do not promote rollout |
| `CONDITIONAL` | Partial pass — operator review required |
| `CERTIFIED` | All checks pass — eligible for FULL_PRODUCTION |
| `LOCKED_DOWN` | Manual or automatic lock — no promotion |

Checks include: no FATAL incidents, worker mesh, replay, queues, recovery, budget, Telegram, event bus, DB, memory trend, poison queue, stability, SLOs.

## Environment

```bash
OPS_CERT_ENABLED=true
OPS_CHAOS_ENABLED=false          # enable only in staging drills
OPS_SLO_ENABLED=true
OPS_CERT_MIN_SCORE=0.85
OPS_AUDIT_HMAC_SECRET=...        # production HMAC for signed actions
```

## Production procedures

1. Run `/certification_status` — resolve all blockers.
2. Run `/go_live_certify` — confirm `CERTIFIED`.
3. Run `/go_live_check` (live ops) — confirm readiness.
4. Promote rollout stage per `PRODUCTION_GO_LIVE_CHECKLIST.md`.
5. Enable chaos drills in staging only before production.
6. Monitor `/slo_live` and `/error_budget` during first 24h.
7. Daily `/exec_report` for executive visibility.

## Chaos drill checklist

- [ ] Staging: `OPS_CHAOS_ENABLED=true`
- [ ] Run each scenario once; survivability ≥ 0.55
- [ ] Verify auto-rollback triggers on `worker_crash` with low health
- [ ] Confirm no FATAL incidents after drill window
- [ ] Disable chaos before public go-live

## Related docs

- `docs/LIVE_OPS_ARCHITECTURE.md`
- `docs/PRODUCTION_GO_LIVE_CHECKLIST.md`
- `docs/RELIABILITY_RUNBOOK.md`
