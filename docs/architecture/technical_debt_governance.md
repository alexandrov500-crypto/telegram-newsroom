# Technical debt governance

Classification and handling rules — not a backlog dump.

## Acceptable debt

- Intentional single-node limits
- Heuristic forecasts (v1.9) with documented confidence limits
- Manual ops history (`var/ops_history/`) instead of telemetry backend
- SQLite WAL maintenance by operator schedule
- Static HTML dashboard vs live metrics server

**Rule:** acceptable if documented, bounded, and has a runbook.

## Operational debt

Debt that increases operator toil without code smell:

| Example | Remediation |
|---------|-------------|
| Unpruned `OUTPUT_DIR` | Retention CLI + schedule |
| Stale backups | Freshness checks in recovery intelligence |
| Missing drift baseline | `RUNTIME_DRIFT_MONITOR=1` + capture |
| Skipped nightly inspection | Release gate discipline |

Prioritize operational debt over refactors.

## Architectural debt

Structural choices that may need ADR to change:

- Single SQLite writer assumption
- Redis as optional queue transport
- Publish lock semantics
- 14-artifact inspection model

**Do not “fix” architectural debt casually** — use [evolution_decision_matrix.md](evolution_decision_matrix.md).

## Deferred complexity

Explicitly parked ideas (RFC / POST_V1 backlog):

- Multi-region active-active
- Microservice boundaries
- Mandatory observability stack

Status: deferred until measured pain + v2 gates.

## Intentional limitations

Documented non-goals ([ENGINEERING_PHILOSOPHY.md](../ENGINEERING_PHILOSOPHY.md), [unsupported_deployments.md](../scalability/unsupported_deployments.md)):

- Not a workflow engine
- Not HA by default
- Not multi-tenant SaaS platform

These are **features of the design**, not debt.

## Never fix areas (without v2)

- Rewriting observability as microservices
- Replacing Makefile operator UX with opaque SaaS
- Auto-scaling control plane in-repo
- ML-based ops automation

## Only if measured pain areas

| Area | Measurement |
|------|-------------|
| PostgreSQL migration | WAL/lock pain, writer contention, restore SLAs missed |
| More workers | Queue sustained >200 with healthy upstream |
| New artifact type | Inspection gap proven in incidents |
| Breaking schema | External API mandate |

Requires ADR + complexity budget approval.

## Debt review cadence

- **Quarterly:** scan operational debt (disk, backups, runbooks)
- **Release:** `make governance-validate` + architecture guardrails
- **Annual:** v2 gate review — is major version still unjustified?
