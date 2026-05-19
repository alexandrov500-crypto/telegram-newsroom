# Production Readiness Certification

## Purpose

Formal gates before promoting staging → production. Complements architecture-complete cognitive/mesh/epistemic layers with **operational evidence**.

## SLO targets (`bot/operations/types.py`)

| SLO | Target |
|-----|--------|
| Editorial queue backlog | ≤ 500 |
| Epistemic stability | ≥ 0.65 |
| Mesh health | ≥ 0.60 |
| Replay divergence | ≤ 0.15 |
| Storage growth | ≤ 200 MB/day |
| Daily AI budget | ≤ $50 (configurable) |
| Operator alert fatigue | ≤ 12/hour |

## Automated certification

```bash
python3 -m bot.operations.cli certify
python3 -m bot.operations.cli certify --skip-chaos   # SLO-only
```

Gates: backlog, epistemic stability, mesh health, replay integrity, storage sustainability, optional chaos suite.

Results stored in `ops_certification_runs`.

## Staging environment

```bash
cp deploy/staging/env.staging.example .env
# configure secrets
bash deploy/staging/bootstrap-staging.sh
bash deploy/staging/validate-staging.sh
```

Topology: `ingest-eu`, `ingest-us`, `ingest-apac`, `signal`, `digest`, `operator` + Postgres, Redis, Prometheus, Grafana, Tempo.

Dashboard: **Staging Readiness** (`deploy/grafana/dashboards/staging-readiness.json`).

## Long-running burn-in

```bash
python3 -m bot.operations.cli burnin-start --profile 7d
```

Set `OPS_BURNIN_ENABLED=true` on operator nodes for automatic 7d profile.

Samples in `ops_burnin_samples`; regression analysis via `BurnInRunner.analyze_baseline()`.

Profiles: `24h`, `7d`, `30d`.

## Real feed validation

```bash
python3 -m bot.operations.cli validate-feeds
```

Catalog in `bot/operations/feed_validation.py` (Reuters, AP, BBC, DW, noisy variants).

Tracks: reliability, malformed payloads, duplicate bursts, encoding repair.

## Storage sustainability

```bash
python3 -m bot.operations.cli storage-maintain
```

Retention policies in `StorageSustainability.RETENTION_DAYS`; audit in `ops_compaction_log`.

## Failure archaeology

Incident bundles in `ops_incident_bundles` via `FailureArchaeology.capture()` — timeline, cognitive state, topology, governance, operator actions, RCA summary.

## Operator commands

| Command | Purpose |
|---------|---------|
| `/ops` | Burn-in + certification status |
| `/triage` | Prioritized alert queue |
| `/review` | Editorial usefulness scoring |
| `/feeds` | Feed health report |

## Production deployment playbook

1. Run 7-day burn-in on staging cluster
2. `validate-staging.sh` green
3. `certify` all gates pass
4. Review `/triage` fatigue and epistemic alerts
5. Editorial review panels show usefulness ≥ 0.6
6. Sign off in `docs/BURN_IN_REPORT.md` evidence log
7. Promote with `deploy/docker-compose.prod.yml` or K8s manifests

## Local development

Operations platform runs against SQLite when DB initializes successfully; full staging requires Docker compose stack.

## Related docs

- [BURN_IN_REPORT.md](BURN_IN_REPORT.md)
- [FAILURE_DRILLS.md](FAILURE_DRILLS.md)
- [FEDERATED_COGNITIVE_MESH.md](FEDERATED_COGNITIVE_MESH.md)
- [EPISTEMIC_INTEGRITY_LAYER.md](EPISTEMIC_INTEGRITY_LAYER.md)
