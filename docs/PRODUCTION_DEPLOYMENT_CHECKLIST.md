# Production deployment checklist

Use after staging burn-in (7d+) and operator signoff.

## Pre-promotion

- [ ] `python -m bot.operations.cli validate-staging` exit 0
- [ ] `python -m bot.operations.cli nightly-cert` staging score ≥ 0.75
- [ ] `docs/BURN_IN_REPORT_AUTO.md` shows no regressions
- [ ] Grafana staging-readiness: all SLO panels green 72h
- [ ] Operator signoff recorded (`docs/staging/operator_staging_signoff.md`)
- [ ] Incident export tested (`incident-export` CLI)
- [ ] Rollback playbook reviewed (`docs/PRODUCTION_ROLLBACK.md`)

## Deploy

- [ ] Secrets in vault (not in git)
- [ ] `DATABASE_URL` / `REDIS_URL` production endpoints
- [ ] `OPS_BURNIN_ENABLED=true` on first production week
- [ ] Prometheus + Grafana + Tempo wired
- [ ] On-call runbook distributed (`docs/OPERATOR_RUNBOOK.md`)

## Post-deploy (24h)

- [ ] `/self-check` and `/ready` healthy
- [ ] No cost anomaly alerts
- [ ] Epistemic longitudinal stable
- [ ] Replay divergence < SLO

## Signoff

| Role | Name | Date |
|------|------|------|
| Operator lead | | |
| Platform | | |
