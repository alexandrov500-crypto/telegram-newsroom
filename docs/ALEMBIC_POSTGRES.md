# Alembic and PostgreSQL

## Driver mapping

The application uses **async** SQLAlchemy URLs:

- Development / tests default: `sqlite+aiosqlite:///...`
- Production scaling: `postgresql+asyncpg://user:pass@host:5432/dbname`

Alembic runs **synchronous** migrations. `alembic/env.py` maps URLs via `utils.database_url.alembic_sync_url_from_async`:

- `sqlite+aiosqlite` → `sqlite`
- `postgresql+asyncpg` → `postgresql+psycopg` (Psycopg 3)

Install `psycopg[binary]` (already in `requirements.txt`) so `alembic upgrade head` works against PostgreSQL.

## Commands

```bash
export DATABASE_URL=postgresql+asyncpg://user:pass@localhost:5432/newsroom
alembic upgrade head
```

For SQLite file URLs, the same command applies; the env module normalizes drivers.

## SQLite → PostgreSQL data migration

1. Stop writers to the old SQLite database.
2. Create an empty PostgreSQL database and run `alembic upgrade head` against it.
3. Use `pg_dump`-style logical migration or a one-off ETL script to copy tables (`raw_posts`, `drafts`, `published_posts`, …). Types are compatible (UTC datetimes, integers, text).
4. Point `DATABASE_URL` at PostgreSQL and start a **single** instance first; verify `/ready` or `python -m tools.admin_cli runtime-health`.
5. Enable `REDIS_ENABLED=true` before running multiple publisher-facing processes so locks and optional idempotency keys are shared.

There is no built-in `sqlite3` → `pg` auto-migration in this repo; use standard DB tools to avoid silent data loss.
