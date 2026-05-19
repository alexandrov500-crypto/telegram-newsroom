# Incident response guide

## Severity

| Level | Examples | Response time |
|-------|----------|---------------|
| SEV-1 | Publish storm, data loss risk | Immediate |
| SEV-2 | Epistemic SLO breach, federation partition | < 1h |
| SEV-3 | Feed degradation, cost warning | < 24h |

## Workflow

1. **Detect** — Grafana alert or `/triage`
2. **Stabilize** — bounded autonomy holds; use operator overrides
3. **Export** — `/incident <key>` or `python -m bot.operations.cli incident-export <key>`
4. **Reconstruct** — open `/ops/explorer/replay` and incident bundle JSON
5. **RCA** — use bundle `rca_summary` + archaeology timeline
6. **Recover** — apply rollback if needed (`docs/PRODUCTION_ROLLBACK.md`)
7. **Postmortem** — `docs/operations/postmortem_template.md`

## Deterministic replay

Incident bundles include timeline, cognitive state, contradictions, and trust snapshots. Re-run certification:

```bash
python -m bot.operations.cli certify --skip-chaos
```

## Operator supremacy

All autonomous remediation is bounded. Trust overrides and contradiction resolutions require explicit operator action.
