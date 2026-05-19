# PostgreSQL Unification Plan (Design Only)

## Goal

Single production persistence layer: **async SQLAlchemy + PostgreSQL**, while **SQLite remains the default for local dev**.

## Current state

- **Editorial domain**: sync SQLite repositories (`bot/storage/*`)
- **Cluster coordination**: SQLite or psycopg sync (`CoordinationRepository`)
- **Sourced events / workflows / publish receipts**: SQLite tables in `newsroom.db`
- **App stack** (`db/`): async SQLAlchemy already exists for drafts/workers

## Migration phases

### Phase 1 — Shared cluster + stream metadata (low risk)

- Move `cluster_*`, `sourced_event_log`, `workflow_*`, `publish_receipts` to PostgreSQL only
- Nodes already use `DATABASE_URL` for coordination
- Bot editorial stays on SQLite file in dev

### Phase 2 — Dual-write sourced events

- Write `sourced_event_log` to PG + SQLite (feature flag `SOURCED_PG_DUAL_WRITE`)
- Replay verification: compare sequence counts

### Phase 3 — Read path cutover

- Read projections from PostgreSQL
- SQLite becomes cache/offline export only

### Phase 4 — Editorial repositories

- Introduce `AsyncEditorialRepository` behind interface
- Migrate highest-churn tables: `pending_news`, `signals`, `stories`
- Alembic migrations per domain

### Phase 5 — Decommission SQLite in production

- Keep SQLite for `APP_ENV=development` only
- CI runs both backends

## Compatibility strategy

- Repository factory: `create_repositories(settings) -> Repositories`
- URL detection via `utils/database_url.py`
- No breaking changes to handler signatures during Phase 1–3

## Rollback plan

- Feature flags per phase (`PG_SOURCED_READ`, `PG_EDITORIAL_READ`)
- Dual-write window allows revert to SQLite-only reads
- Alembic downgrade scripts for each migration

## Zero-downtime considerations

- Expand contract: add PG columns/tables before cutover
- Blue/green nodes: old nodes on SQLite, new on PG during dual-write
- Leader-elected migration jobs (reuse `cluster_job_leases`)
- Connection pooling: `pool_pre_ping`, `pool_size=5`, `max_overflow=10` (match `db/session.py`)

## Not in scope yet

- Full CQRS projection rebuild
- ClickHouse / Timescale analytics (interfaces in `bot/distributed/interfaces.py`)
