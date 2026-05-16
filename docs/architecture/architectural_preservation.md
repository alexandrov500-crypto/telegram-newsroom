# Architectural preservation policy

Long-term stewardship rules for the production-lite Telegram newsroom platform. **Strategy only** — not a v2 implementation plan.

## Core architectural invariants

These must survive major versions unless an explicit ADR + migration program overturns them with operator sign-off:

1. **Single-node-first** — default deploy is one host, one operator mental model.
2. **Frozen inspection contracts** — 14 `runtime/*.json` artifacts, schema v1, 11 inspection CLIs (until a declared major bump).
3. **Deterministic recovery** — shell-first, JSON evidence, reproducible verify/recovery paths.
4. **Opt-in behavior change** — production semantics change via env flags default **off**.
5. **No mandatory control plane** — no required K8s, Prometheus, Vault, or external workflow engine for core ops.
6. **SQLite as default datastore** — Postgres only via documented evolution gate ([postgresql_evolution_path.md](../scalability/postgresql_evolution_path.md)).
7. **Operator agency** — advisory intelligence; no autonomous destructive remediation.

## Simplicity preservation rules

- Prefer extending existing modules over new subsystems.
- One concern per ADR; no “platform initiative” bundling.
- CLI and Makefile remain the primary operator interface.
- Documentation changes are the default vehicle for operational improvement.
- New dependencies require justification in ADR or complexity budget.

## Bounded complexity principles

- Every new component pays into [complexity_budget.md](complexity_budget.md).
- If operational burden increases without measured pain reduction, reject or defer.
- Cap recommendation/alert noise (see v1.9 intelligence caps).
- No second parallel governance framework inside the repo.

## Operational-first principles

- If it does not improve inspect, recover, or maintain — defer.
- Release gates (`make release-check`) trump feature velocity.
- Failure modes must be documented before new failure modes are introduced.
- Scaling guidance is honest ([future_scalability_realities.md](future_scalability_realities.md)).

## Anti-platform-creep rules

| Creep pattern | Response |
|---------------|----------|
| “We need a small service mesh” | Reject unless T4 experimental, unsupported |
| “Let's add mandatory Grafana” | Reject; static dashboard / JSON artifacts only |
| “Microservice for publish” | ADR + v2 gate; not incremental |
| “Auto-heal workers in code” | Reject; runbooks + operator action |
| “Feature flags default on” | Reject without major version |

## Do not rewrite policy

Full rewrites are **out of scope** unless:

- Measured multi-quarter pain documented
- Complexity budget and evolution matrix approved
- Migration + rollback tested on copies
- Operator continuity plan accepted

Incremental hardening (v1.1–v1.9 pattern) is the default evolution mode.

## Acceptable evolution boundaries

| In scope (1.x / stewardship) | Out of scope (without v2 program) |
|------------------------------|-----------------------------------|
| Docs, runbooks, read-only tools | Distributed multi-node SQLite |
| Opt-in flags, diagnostics | Mandatory Postgres |
| Bounded tests (chaos, soak, intelligence) | Event-bus platform |
| ADRs, governance docs | Kubernetes-native redesign |
| Operator history samples (manual) | Autonomous orchestration |

See [v2_transition_strategy.md](v2_transition_strategy.md) for what would justify a true major version.
