# PostgreSQL evolution path (documentation only)

**v1.8 does not implement PostgreSQL.** This document defines a controlled future evolution gate.

## Why SQLite Still Exists

- Single-node-first production-lite model
- Zero external DB ops for default deploy
- Frozen runtime evidence and inspection CLIs assume file-local DB
- One-writer semantics match current worker architecture

## Real Scaling Pain Points

| Pain point | SQLite limit | Postgres would address |
|------------|--------------|------------------------|
| Concurrent writers | Single writer | Multiple connections |
| WAL checkpoint coupling | Large WAL blocks maintenance | Different WAL/ops model |
| Cross-node DB access | Unsupported (T4) | Remote DB |
| Very large tables | Vacuum/checkpoint ops | Managed ops |

Many throughput limits are **API and publish-lock bound**, not SQLite alone.

## Migration Preconditions

Before any Postgres program:

1. ADR approved; explicit non-goal review completed
2. Dual-write or outage window strategy defined **outside** v1.8 scope
3. Schema migration tooling and rollback tested on copy
4. Runtime contract impact assessment (14 frozen artifacts unchanged unless version bump)
5. Evidence/snapshot compatibility plan
6. Operator runbook for connection pooling, backups, secrets

## Operational Complexity Tradeoffs

| Area | SQLite (current) | PostgreSQL |
|------|------------------|------------|
| Backup | File copy + quiesce | pg_dump / managed backup |
| Local dev | trivial | container or service |
| HA | not in scope | external Patroni/cloud |
| Migrations | app migrations | coordinated DBA window |

## Rollback Risks

- Partial migration leaves hybrid schemas — **unsupported**
- Data divergence if dual-write implemented incorrectly
- Evidence tools reading wrong DSN
- Rollback window closes after destructive transforms

## Hybrid Unsupported States

- SQLite + Postgres both receiving writes
- Some workers on SQLite, some on Postgres
- Read replica without documented lag handling in publish path

## Non-Goals

- Mandatory PostgreSQL migration in v1.8
- Automatic migration scripts in repo
- Kubernetes-first database operators
- Event-sourced rewrite as migration side effect
- Microservice per bounded context

## Recommended decision gate

Stay on SQLite while T1/T2 envelope satisfied. Revisit Postgres only when **documented** pain (not dev convenience) exceeds operational cost — see [scaling_governance.md](scaling_governance.md).
