# Trust certification and evolution safety

Long-term trustworthiness, behavioral regression, and safe runtime evolution.

## Behavioral regression

Deterministic offline comparison of governance/ranking/publish/drift snapshots vs baseline.

```bash
python -m tools.behavior_regression
python -m tools.behavior_regression --hours 48 --save-baseline
```

Output: `{RUNTIME_STATE_DIR}/trust/behavior_regression_report.json`

Env: `BEHAVIOR_REGRESSION_WINDOW_HOURS` (default 24), `BEHAVIOR_REGRESSION_MAX_DIFFS` (default 12).

## Trust certification

Daily artifact (heartbeat): `trust/trust_certification_YYYYMMDD.json`

Includes SLO compliance, validation checks, regression pass, drift baseline, recovery drill, operator interventions.

## Evolution safety gates

`POST /ops/control/evolution/validate` with body:

```json
{"change_type": "ranking_weights", "payload": {"weights": {...}}}
```

Validates schema, JSON policy files, migration version, behavior regression threshold.

On failure: structured log `runtime.evolution.validation.failed`.

Mode changes (`/ops/control/mode`, `/ops/control/economic/mode`) run gates automatically.

## Canary mode

`RUNTIME_CANARY_ENABLED=1` — compares live vs `editorial/ranking_weights_canary.json` (hash + order metadata). No production mutation.

`GET /runtime/canary/status`

## Governance drift baselines

EMA baselines in `trust/governance_drift_baselines.json`. Warnings: `governance.baseline.warning`.

## Autonomous validation

Heartbeat: `trust/autonomous_validation_report.json` (publish journal, snapshots, migrations, policy, audit chain).

## Evolution journal

Append-only `trust/evolution_journal.jsonl` — deployments, modes, policies.

`GET /runtime/evolution/history?limit=100&event_type=operational_mode`

## Certification HTTP

| Endpoint | Content |
|----------|---------|
| `GET /runtime/certification/trust` | Latest trust certification |
| `GET /runtime/certification/regressions` | Behavior regression report |
| `GET /runtime/certification/validation` | Autonomous validation |
| `GET /runtime/certification/drift` | Drift vs baseline |
| `GET /runtime/canary/status` | Canary state |
| `GET /runtime/evolution/history` | Evolution journal |

All require ops token when `OPS_HTTP_TOKEN` is set.
