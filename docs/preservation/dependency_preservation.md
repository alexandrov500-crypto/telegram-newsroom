# Dependency preservation strategy

Minimum discipline for rare releases and low-activity maintenance.

## Minimum viable dependency set (runtime)

| Tier | Packages | Role |
|------|----------|------|
| Critical | telethon, aiogram, openai, sqlalchemy, aiosqlite | Core pipeline |
| Critical | python-dotenv, pydantic, alembic | Config + schema |
| Operational | redis (if T2), APScheduler | Queue/lock/schedule |
| Optional | asyncpg, psycopg | Postgres path **not** production-lite default |
| Dev-only | pytest, ruff | CI/local — not deploy artifact |

## Optional vs critical

- **Critical:** Removing breaks ingest, publish, or DB.
- **Optional:** Redis — T1 survives without; T2 does not.
- **Dev-only:** Never required on operator single-node runtime if not running tests.

## Pinning expectations

- `requirements.txt` — exact pins for runtime (`==` where practical).
- `requirements-dev.txt` — pinned toolchain.
- `pyproject.toml` — mirrors dependencies; `requires-python` is floor SSOT.

**Do not** floating-pin critical packages on maintenance branches without CI.

## Upgrade discipline

1. One dependency family per PR when possible.
2. `make ci-test` + `make release-check`.
3. CHANGELOG user-visible if operator-facing (Telegram/OpenAI).
4. No drive-by major bumps during dormancy return.

## Do not aggressively modernize

- No “upgrade everything” PRs without measured pain.
- No replacing SQLite “because old.”
- No Python alpha/beta on production path.
- No dropping pins to “latest compatible” without test evidence.

## Frozen compatibility philosophy

- Application behavior: frozen via ADR-015 + opt-in flags.
- Dependency versions: **pinned but upgradable** — not immortal.
- Evidence/snapshot schema: frozen until major version.

## Sunset policy (dependencies)

| Event | Action |
|-------|--------|
| Security CVE on pinned dep | Patch pin + release note |
| Python EOL | Planned uplift ADR note |
| Telethon/aiogram major | Spike branch + operator comms |
| OpenAI breaking API | Config + handler fix; document model |

See [preservation_governance.md](preservation_governance.md).
