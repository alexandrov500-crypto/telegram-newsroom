# RFC-005: PostgreSQL migration path

**Status:** Draft · **Target:** v1.2+ opt-in

## Problem

`tools/backup_cli.py` only supports SQLite file backup/restore. `deploy/docker-compose.postgres.yml` exists but is not the production-lite default.

## Proposal

**Phase A (docs):** Runbook: pg_dump/pg_restore, stop workers, migrate Alembic.

**Phase B (opt-in):** `backup_cli backup-create --engine postgres` invoking pg_dump when `DATABASE_URL` is postgres.

**Phase C:** Qualification tests in CI matrix (RFC-009) with postgres service.

## Migration risk

**High** — dual-write period, Telethon session still local, runtime JSON still file-based.

## Frozen contract note

Runtime inspection artifacts remain file-based under `OUTPUT_DIR`; Postgres does not replace nightly JSON model.
