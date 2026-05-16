# Start here

Onboarding map for engineers, operators, and reviewers.

## Stable v1.0.0 — operational freeze

> **Runtime governance and inspection model are considered operationally frozen as of v1.0.0** (`RELEASE_STATUS=stable`).
>
> Stabilization over expansion · compatibility-first maintenance · bounded complexity.
>
> Guarantees: [STABILITY_GUARANTEES.md](STABILITY_GUARANTEES.md) · Release gate: `make release-check`

## What this project is

A **production-lite** Telegram newsroom: collect posts (Telethon), cluster/summarize (OpenAI), moderate via admin bot (aiogram), publish to a target channel. Operational maturity comes from **deterministic JSON artifacts**, shell-first CLIs, and frozen inspection contracts — not from a platform control plane.

## What this project intentionally is NOT

- Not a Kubernetes / cloud-native platform repo
- Not a metrics warehouse (no mandatory Prometheus/Grafana)
- Not a workflow orchestration engine
- Not a deployment automation system (release discipline over deploy bots)
- Not an extensible governance framework (contracts are frozen per ADR-015)

## If you only read 3 docs

1. [ENGINEERING_PHILOSOPHY.md](ENGINEERING_PHILOSOPHY.md) — why the system is shaped this way  
2. [OPERATOR_QUICKSTART.md](OPERATOR_QUICKSTART.md) — inspect runtime in minutes  
3. [ARCHITECTURE_MAP.md](ARCHITECTURE_MAP.md) — flows and doc topology  

**Maintenance:** [MAINTENANCE_MODE.md](MAINTENANCE_MODE.md) · [ISSUE_TRIAGE.md](ISSUE_TRIAGE.md) · `make release-check`  
**Future planning (not v1.0.x scope):** [post_v1_hardening.md](post_v1_hardening.md) · [POST_V1_TODO_BACKLOG.md](POST_V1_TODO_BACKLOG.md)  
**v1.1 validation:** [v1_1_operational_validation_report.md](v1_1_operational_validation_report.md) · `make chaos-test` · [runbooks/](runbooks/)  
**v1.3 resilience:** [v1_3_operational_envelope.md](v1_3_operational_envelope.md) · `make soak-test` · `make resilience-validate`  
**v1.4 governance:** [compatibility_policy.md](compatibility_policy.md) · [release_governance.md](release_governance.md) · `make governance-validate`  
**v1.6 security:** [security/secrets_hygiene.md](security/secrets_hygiene.md) · `SECURITY_REDACTION=1` · `make security-validate`  
**v1.8 scalability:** [scalability/operational_topologies.md](scalability/operational_topologies.md) · `make scalability-validate` · [runbooks/scaling/](runbooks/scaling/)  
**v1.9 intelligence:** [operational_intelligence.md](operational_intelligence.md) · `make intelligence-validate` · `make ops-summary`  
**v2 stewardship:** [architecture/v2_transition_strategy.md](architecture/v2_transition_strategy.md) · `make architecture-validate`  
**v2.x semantics:** [semantics/operational_invariants.md](semantics/operational_invariants.md) · `make semantics-validate`  
**Historical traceability:** [stewardship/adr_lineage_map.md](stewardship/adr_lineage_map.md) · `make traceability-validate`  
**Preservation readiness:** [preservation/ecosystem_aging.md](preservation/ecosystem_aging.md) · `make preservation-validate`  
**Legacy stewardship:** [legacy/legacy_state_definition.md](legacy/legacy_state_definition.md) · `make legacy-validate`  
**Live Telegram validation:** [live_validation/live_telegram_validation_plan.md](live_validation/live_telegram_validation_plan.md) · `make live-validation-validate`  
**Production ops (v3):** [operations/retry_error_matrix.md](operations/retry_error_matrix.md) · [operations/publish_idempotency.md](operations/publish_idempotency.md)  
**Staging / rollout (v3.1):** [staging/staging_environment_checklist.md](staging/staging_environment_checklist.md) · [operations/production_lite_rollout.md](operations/production_lite_rollout.md) · `make staging-validate`  
**Production activation:** [runbooks/controlled_activation.md](runbooks/controlled_activation.md) · [operations/72h_stability_window.md](operations/72h_stability_window.md) · `make production-validate`

## For operators

| Goal | Doc / command |
|------|----------------|
| Deploy single node | [DEPLOYMENT_QUICKSTART.md](DEPLOYMENT_QUICKSTART.md) |
| Daily inspection | `make runtime-help` · [OPERATOR_QUICKSTART.md](OPERATOR_QUICKSTART.md) |
| Demo narrative | [DEMO_WALKTHROUGH.md](DEMO_WALKTHROUGH.md) |
| Release gate | [RELEASE_CHECKLIST.md](RELEASE_CHECKLIST.md) |
| Failure playbooks | [examples/runtime_failure_investigation.md](examples/runtime_failure_investigation.md) |

Example scripts (dry-run by default): [../examples/demo_walkthrough/](../examples/demo_walkthrough/)

## For contributors

| Goal | Doc / command |
|------|----------------|
| Local setup | [QUICKSTART.md](QUICKSTART.md) · [CONTRIBUTING.md](CONTRIBUTING.md) |
| Tests | `make ci-test` |
| Contract freeze | [architecture/RUNTIME_CONTRACTS.md](architecture/RUNTIME_CONTRACTS.md) |
| Do not expand governance | [architecture/RUNTIME_MATURITY.md](architecture/RUNTIME_MATURITY.md) |

## For architecture review

| Goal | Doc |
|------|-----|
| System scope | [architecture/SYSTEM_OVERVIEW.md](architecture/SYSTEM_OVERVIEW.md) |
| ADR index | [architecture/README.md](architecture/README.md) |
| Lifecycle | [architecture/OPERATIONAL_LIFECYCLE.md](architecture/OPERATIONAL_LIFECYCLE.md) |
| Frozen contracts | [architecture/RUNTIME_CONTRACTS.md](architecture/RUNTIME_CONTRACTS.md) |
| Stabilization | [architecture/ADR-015-runtime-stabilization-and-contract-freeze.md](architecture/ADR-015-runtime-stabilization-and-contract-freeze.md) |

## 5-minute repo tour

```
telegram-newsroom/
├── app/              # Entry: python -m app.main
├── observability/    # Frozen runtime JSON builders (inspection only)
├── newsroom/cli/     # Inspection CLIs (health, verify-runtime, runtime-index, …)
├── tools/            # runtime_ops.py, preflight, qualification, …
├── tests/
│   ├── runtime/      # Ops module tests
│   ├── smoke/        # Artifact smoke tests
│   └── contracts/    # Frozen layout + docs navigation
├── deploy/           # production-lite templates (Compose, systemd, env)
├── examples/
│   ├── runtime_samples/   # Sanitized JSON
│   ├── demo_outputs/      # Sanitized CLI transcripts
│   └── demo_walkthrough/  # Commented shell scripts
└── docs/             # START_HERE.md (you are here)
```

## Architecture map

See [ARCHITECTURE_MAP.md](ARCHITECTURE_MAP.md) for ASCII flows: runtime, inspection, validation, release, deployment.

## Runtime inspection flow

```bash
export OUTPUT_DIR=./runtime_ops_output
make runtime-nightly RUNTIME_DIR=./var/runtime OUTPUT_DIR="$OUTPUT_DIR"
make runtime-index OUTPUT_DIR="$OUTPUT_DIR"
make verify-runtime OUTPUT_DIR="$OUTPUT_DIR"
```

Or: `make demo-runtime` for the suggested sequence (prints commands).

## Deployment entrypoints

- Local: `.env.example` → `.env` → `python -m app.main`
- Host: `deploy/example.env.production-lite`
- Compose: `deploy/docker-compose.production-lite.yml`
- Scheduled ops: `deploy/systemd/newsroom-nightly.timer`

## Suggested reading order

1. This file  
2. [OPERATOR_QUICKSTART.md](OPERATOR_QUICKSTART.md) (operators) or [QUICKSTART.md](QUICKSTART.md) (developers)  
3. [OPERATIONAL_CONFIDENCE.md](OPERATIONAL_CONFIDENCE.md) — what is validated for v1.0.0  
4. [ARCHITECTURE_MAP.md](ARCHITECTURE_MAP.md) — flows (single page)  
5. [MAINTENANCE_MODE.md](MAINTENANCE_MODE.md) (maintainers)  
6. [FAQ.md](FAQ.md) as needed  

Deep reference: [RUNTIME_OPS.md](RUNTIME_OPS.md), [REPRODUCIBILITY.md](REPRODUCIBILITY.md), [REPOSITORY_MAP.md](REPOSITORY_MAP.md).

**Makefile:** `make docs-map` · **Burn-in:** [BURN_IN_REPORT.md](BURN_IN_REPORT.md) · **Drills:** [FAILURE_DRILLS.md](FAILURE_DRILLS.md)

**Shell helpers:** `scripts/runtime_sanity_check.sh` · `scripts/runtime_snapshot.sh` · `scripts/runtime_restore.sh`
