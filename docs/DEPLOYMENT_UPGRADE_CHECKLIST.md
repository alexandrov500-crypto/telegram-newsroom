# Deployment upgrade checklist

Use before/after each production-lite rollout.

## Pre-flight

- [ ] Read `CHANGELOG.md` for this version.
- [ ] `git fetch && git checkout <tag>` (or merge PR) on the server.
- [ ] Backup DB + `RUNTIME_STATE_DIR` (`docs/BACKUP_AND_RECOVERY.md`).
- [ ] `python -m tools.admin_cli config-doctor --preview-missing` (CI or local) — no missing vars.
- [ ] Note `app_version` / schema fields from `app/versioning.py` vs previous deploy.

## Apply

- [ ] Install deps: `pip install -r requirements.txt` (or rebuild image).
- [ ] `alembic upgrade head` when migrations ship.
- [ ] Restart **Redis** (if any) before app/workers.
- [ ] Restart application processes (`app.main`, workers) with same `NEWSROOM_QUEUE_PREFIX` / Redis DB index as before unless intentionally isolating a new stack.

## Post-flight

- [ ] `curl` `/ready` or `python -m tools.admin_cli runtime-health --json`.
- [ ] `python -m tools.admin_cli runtime-integrity-check` — exit 0.
- [ ] Spot-check logs: `startup.banner`, first pipeline tick, no repeated `redis.transport_retry` without `recovered`.
- [ ] Optional: `python -m tools.admin_cli export-ops-dashboard --out var/reports/ops-post-upgrade.json --format json`.

## Rollback

- [ ] Re-deploy previous artifact + run forward-compatible DB restore from backup if schema moved.
- [ ] If only app regression: restore previous container/tag; keep DB unless migration already applied — coordinate with migration notes.
