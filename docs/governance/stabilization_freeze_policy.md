# Stabilization freeze policy

Applies during:

- First **72h** after production-lite activation ([72h_stability_window.md](../operations/72h_stability_window.md))
- Any **HIGH** incident until postmortem complete
- Explicit operator-declared stabilization extension

**Goal:** preserve v3.1 runtime stability; allow learning via docs and bounded hotfixes only.

## Prohibited (without ADR + exception approval)

| Category | Examples |
|----------|----------|
| Refactors | Module moves, rename sweeps, “cleanup” PRs |
| Infra rewrites | K8s migration, new message broker |
| Retry redesign | Changing `with_telethon_retries` / `async_retry` semantics |
| Async model changes | New event loops, worker concurrency model |
| Queue redesign | Redis stream migration, new job types |
| Scheduler redesign | Multi-leader, new tick orchestration |
| Schema migrations | Alembic breaking changes, runtime JSON schema |
| Publish semantics | Idempotency rules, chunk strategy, lock TTL behavior |
| Default-on features | New env flags default true |
| Observability servers | Mandatory Prometheus/Grafana |

## Permitted

| Category | Examples |
|----------|----------|
| Documentation | Findings, baselines, discovery, runbooks |
| Observability notes | Baseline tables, ops history archives |
| Incident fixes | **Bounded hotfixes** — minimal diff, tests required |
| Operational tooling | **Read-only** CLIs (diagnostics, verify, inspect) |
| Config (operator) | Within documented T1 envelopes only |
| Contract tests | Doc existence, no runtime artifact change |

## Hotfix criteria

A hotfix is allowed only if ALL true:

1. Production incident or security issue
2. Smallest possible code change
3. No publish/retry semantic change
4. `make ci-test` + `make governance-validate` green
5. Documented in postmortem or ops log
6. Retrospective within 48h

## v3.2 design work

Architecture discovery ([v3_2_discovery.md](../architecture/v3_2_discovery.md)) is **allowed** in docs/ only — no production branch prototypes that alter runtime.

## Exception process

1. Operator + engineering agree in writing (ops log entry)
2. Note governance impact
3. Plan rollback before merge
4. Update [production_governance_audit.md](production_governance_audit.md) if control affected

## Enforcement

- CI: frozen runtime contract tests
- Review: PR template checklist
- Release: `make release-check` before any non-doc tag

## Related

- [STABILITY_GUARANTEES.md](../STABILITY_GUARANTEES.md)
- [ADR-015-runtime-stabilization-and-contract-freeze.md](../architecture/ADR-015-runtime-stabilization-and-contract-freeze.md)
- [v3_2_planning_gate.md](../releases/v3_2_planning_gate.md)
