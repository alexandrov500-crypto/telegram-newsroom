# Operations (production-lite)

Engineering-oriented lifecycle and commands live in **`docs/architecture/OPERATIONAL_LIFECYCLE.md`**. This page lists **copy-paste** entrypoints only.

Recurring tasks for operators and developers: **no orchestration platform** — scripts, Makefile targets, and sequential CLIs only.

## Nightly-style workflow

Deterministic sequential runner (same process, bounded):

```bash
python tools/runtime_ops.py nightly-check \
  --runtime-dir ./var/runtime \
  --output-dir ./runtime_ops_output \
  --baseline ./baselines/runtime_bundle.zip \
  --short-soak \
  --strict
```

Shortcut:

```bash
make runtime-nightly RUNTIME_DIR=./var/runtime OUTPUT_DIR=./runtime_ops_output
```

Details: `docs/RUNTIME_OPS.md`.

## Release qualification

Compare current `runtime_bundle.zip` to a frozen baseline (read-only, deterministic):

```bash
python tools/release_qualification.py \
  --runtime-bundle ./artifacts/runtime_bundle.zip \
  --baseline ./baselines/runtime_bundle.zip \
  --strict
```

Makefile wrapper (requires both paths):

```bash
make release-qualify RUNTIME_BUNDLE=./artifacts/runtime_bundle.zip BASELINE=./baselines/runtime_bundle.zip
```

Human + JSON reports: `--output-report`, `--json-output`. See `docs/RELEASE_QUALIFICATION.md`.

## Operational dashboard

Static HTML (no live server beyond optional file hosting):

```bash
make runtime-dashboard \
  DASHBOARD_OUT=var/reports/operational_dashboard.html \
  RUNTIME_BUNDLE=runtime_ops_output/runtime_bundle.zip \
  QUAL_JSON=runtime_ops_output/qualification.json \
  REGR_JSON=runtime_ops_output/regression.json
```

Or directly:

```bash
python tools/build_operational_dashboard.py \
  --runtime-bundle runtime_ops_output/runtime_bundle.zip \
  --qualification-report runtime_ops_output/qualification.json \
  --regression-report runtime_ops_output/regression.json \
  --output var/reports/operational_dashboard.html
```

See `docs/OPERATIONAL_DASHBOARD.md`.

## Regression workflow

Baseline vs current bundle metrics:

```bash
python tools/compare_runtime_baseline.py --help
```

See `docs/RUNTIME_REGRESSION.md`.

## Artifact retention

Prune old zips/JSON under configured roots (deterministic, no daemon):

```bash
python tools/runtime_retention.py --help
```

See `docs/RUNTIME_RETENTION.md`.

## Runtime preflight (startup readiness)

Full-featured CLI (optional Redis/disk checks):

```bash
python tools/runtime_preflight.py --help
```

Thin Makefile shortcut (defaults only):

```bash
make runtime-preflight RUNTIME_DIR=./var/runtime
```

See `docs/RUNTIME_PREFLIGHT.md`.

## Postmortem workflow (suggested)

1. Preserve logs and `RUNTIME_STATE_DIR` snapshot (`backup_cli` or copy tree).
2. `python -m tools.admin_cli runtime-health --json` (if process still reachable).
3. `python -m tools.admin_cli export-runtime-report --out var/reports/runtime.json`
4. Build bundle + dashboard for offline review (`docs/RUNTIME_ARTIFACTS.md`).
5. Document timeline in your ticket; link git SHA from `app/versioning.py` logs.

## Admin / diagnostics CLI

```bash
python -m tools.admin_cli --help
```

Queue, DLQ, config doctor: see `README.md` (Admin CLI section) and `docs/OPERATIONS_RUNBOOK.md`.

## Runtime degradation & adaptive protection (VPS burn-in)

Long-uptime resilience layer (diagnostics/safety only — no product features):

| Artifact | Purpose |
|----------|---------|
| `var/runtime/runtime_health.jsonl` | Rolling health snapshots (RSS, tick p95, latencies, flags) |
| `var/runtime/runtime_protection_state.json` | `normal` / `elevated` / `degraded` / `critical` + active protections |

**Severity behavior**

- **NORMAL** — full operation
- **ELEVATED** — log warning (`runtime_health_elevated`); PUBLIC GO may warn
- **DEGRADED** — slower scheduler ticks, fewer retries, suppressed non-essential tick metrics
- **CRITICAL** — autonomous publish frozen; ingest + diagnostics continue; `runtime_protection_mode_enabled` logged

Process is **never** auto-terminated.

```bash
make stability-report          # includes runtime_resilience section
make public-go-check           # fails on CRITICAL / memory drift / recovery loops
```

Thresholds (optional `.env`): `RUNTIME_HEALTH_RSS_DRIFT_MB`, `RUNTIME_HEALTH_TICK_P95_SEC`, `PUBLIC_GO_MAX_RSS_DRIFT_MB`, `RUNTIME_PROTECTION_RECOVERY_SAMPLES`.

See also `docs/PIPELINE_EXECUTION.md` (execution graph verification).

## Pre-public launch tooling

```bash
make qa-status              # PREPUBLIC_QA_MODE summary
make incident-report        # continuity + graph + protection snapshot
make release-readiness      # FINAL_PUBLIC_READINESS verdict
make operator-health        # RSS, flags, protection state
make autopublish-status     # auto publish + pause flags
make public-go-check        # includes final readiness gate
make final-release-check    # FINAL_RELEASE_REPORT.json — BLOCKED/CONDITIONAL/APPROVED
make chaos-lite-validate    # controlled recovery pytest subset
```

Docs: [PUBLIC_RELEASE.md](./PUBLIC_RELEASE.md), [PRODUCTION_DEPLOYMENT.md](./PRODUCTION_DEPLOYMENT.md), [INCIDENT_RESPONSE.md](./INCIDENT_RESPONSE.md), [EDITORIAL_OPERATIONS.md](./EDITORIAL_OPERATIONS.md).

Telegram launch ops: `/release_status`, `/burnin_status`, `/go_status`, `/continuity`, `/runtime_state`, `/last_alerts`, `/recent_failures`.

Operator feedback: `app/editorial/operator_feedback.py`, table `operator_feedback`.

### Incident response workflow

1. `make incident-report` — continuity, execution graph, protection snapshot  
2. `make autopublish-status` — auto publish + operator pause flag  
3. `/runtime` and `/anomalies` in Telegram admin chat  
4. If publish stopped: check `publish_gap_hours` in report; `GLOBAL_PUBLISH_PAUSE` and `/pause_autopublish`  
5. CRITICAL protection: autonomous publish frozen until recovery — see `runtime_protection_state.json`  
6. Rollback: [PUBLIC_RELEASE.md](./PUBLIC_RELEASE.md#rollback-procedure)

### Operator feedback workflow

See [EDITORIAL_OPERATIONS.md](./EDITORIAL_OPERATIONS.md). Feedback is advisory; publish still requires gates and (for auto) policy flags.

## Related documentation

| Topic | Doc |
|-------|-----|
| Architecture overview | `docs/architecture/SYSTEM_OVERVIEW.md` |
| Operational lifecycle | `docs/architecture/OPERATIONAL_LIFECYCLE.md` |
| Runbook | `docs/OPERATIONS_RUNBOOK.md` |
| Resilience | `docs/RESILIENCE_AND_FAILURE_MODES.md` |
| Backups | `docs/BACKUP_AND_RECOVERY.md` |
| CI / GitHub Actions | `docs/CI_CD.md` |
| HTTP ops | `docs/WEB_ADMIN.md` |
