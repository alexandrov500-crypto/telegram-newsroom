# ADR lineage map

Chronological decision lineage for maintainers joining years later. **Not legal compliance** — engineering memory.

## Phase map

| Phase | ADRs | Theme | Survived because |
|-------|------|-------|------------------|
| Runtime governance | 001–014 | Inspection JSON, no orchestration | Operators need deterministic ops without platform team |
| Stabilization | 015–017 | Contract freeze, v1.0.0 | Prevent governance explosion |
| Maintenance | 016, 018 | Reproducibility, maintenance-first | Sustainable post-release cadence |
| Post-v1 planning | 019 | Hardening roadmap (docs) | Separate ideas from commitments |
| Reliability | (v1.1 code + RFC-010) | Chaos, retry/lock flags | Measured job loss / publish risk |
| Resilience | (v1.3 + drift ADRs implicit) | Soak, WAL, retention | Long-running single-node reality |
| Release governance | 020 | Compatibility, flags, upgrades | Safe 1.x evolution |
| Security | 021 | Redaction, integrity, trust | Incidents without mandatory Vault |
| Scalability | 022 | T0–T4, bounded scale | Honest limits vs fake HA |
| Intelligence | 023 | Advisory forecasts | Lower operator load without ML ops |
| Stewardship | 024 | v2 gates, preservation | Prevent accidental rewrite |
| Semantics | 025 | Invariants, forbidden states | Reduce ambiguity under failure |
| Traceability | 026 | Stewardship lineage, archaeology | Maintainer succession after years |
| Preservation | 027 | Long-horizon survivability | Dormancy + dependency aging |
| Legacy | 028 | Controlled sunset / legacy state | Abandonment + rewrite pressure |

## ADR chronology (accepted)

| ADR | Decision | Alternatives rejected | Still binding |
|-----|----------|----------------------|---------------|
| 001 | Bounded runtime state | Unbounded event logs | Yes |
| 002 | Static dashboard | Live Grafana requirement | Yes |
| 003 | No workflow engine | Airflow/Temporal in-repo | Yes |
| 004–014 | Inspection artifact pipeline | Ad-hoc ops scripts only | Yes (frozen set) |
| 015 | Contract freeze | Continuous new artifact types | Yes |
| 016 | Reproducibility docs | “Works on my machine” | Yes |
| 017 | v1.0 operational freeze | Feature-first post-release | Yes |
| 018 | Maintenance mode | Expansion-first default | Yes |
| 019 | Planning-only hardening | Immediate microservices | Yes (scope) |
| 020 | Release governance | Ad-hoc tagging | Yes |
| 021 | Opt-in security | Mandatory secrets platform | Yes (opt-in) |
| 022 | Scalability docs | K8s-first redesign | Yes (bounds) |
| 023 | Intelligence tooling | Autonomous remediation | Yes (advisory) |
| 024 | v2 transition gates | Perpetual 1.x feature dump | Yes |
| 025 | Semantics verification | Formal methods platform | Yes |
| 026 | Historical traceability | Compliance archive / git rewrite | Yes |
| 027 | Preservation readiness | Vendoring / offline mirror | Yes |
| 028 | Legacy stewardship | Shutdown automation / archive-only | Yes |

## Cross-links

- RFC index: [../rfc/README.md](../rfc/README.md)
- Validation reports: `v1_1` … `v1_9`, `v2x_*` under `docs/`
- Stewardship index: [decision_archaeology_index.md](decision_archaeology_index.md)

## Preserved non-goals (survived all phases)

- Kubernetes-native platform
- Mandatory PostgreSQL
- Microservice decomposition
- Event-bus migration
- Autonomous orchestration
- Enterprise compliance archive

## How to extend

New accepted ADR → add row here + [architecture/README.md](../architecture/README.md) + run `make traceability-validate`.
