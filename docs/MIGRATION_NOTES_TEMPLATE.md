# Migration notes — template

**Alembic revision(s):** `xxxx_yyyy_description`

## Data migration

- None / describe backfills.

## Rollback

- Safe: yes/no
- `alembic downgrade` target: `<revision>` or N/A

## Operator actions

- [ ] Run `alembic upgrade head`
- [ ] Restart workers after API process
- [ ] Verify `runtime-integrity-check`
