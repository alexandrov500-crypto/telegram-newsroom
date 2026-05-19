# Operator runbook

## Daily shift (15 min)

1. `curl /ready` and `/self-check`
2. Telegram `/dashboard` — consolidated alerts
3. Grafana staging-readiness overview
4. `/triage` — resolve or escalate top items
5. `/feeds` — confirm ingestion reliability

## Weekly

- `bash scripts/burnin_report.sh`
- Review `docs/BURN_IN_REPORT_AUTO.md`
- `bash scripts/nightly_cert.sh`
- Storage: `python -m bot.operations.cli storage-maintain`

## Commands

| Command | Purpose |
|---------|---------|
| `/ops` | Burn-in + certification status |
| `/dashboard` | Deduped alert summary |
| `/triage` | Prioritized open alerts |
| `/session start triage` | Track operator workload |
| `/session end <id>` | Close session + fatigue score |
| `/incident <key>` | Forensic JSON bundle |
| `/contradictions_queue` | Epistemic triage queue |
| `/review` | Editorial usefulness scoring |

## Web explorers

- `http://<host>:8080/ops/` — replay, contradictions, epistemic, incidents
- `/ops/api/export` — JSON for automation

## Escalation

- Misinformation / epistemic: resolve within 4h
- Cost anomaly: switch to low-cost profile (automatic recommendation in `/ops`)
- SEV-1: export incident, page platform, initiate rollback if needed

See `docs/INCIDENT_RESPONSE.md` and `docs/SLO_HANDBOOK.md`.
