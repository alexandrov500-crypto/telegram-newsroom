# Deprecation policy

Controlled removal and evolution without silent operator breakage.

## Deprecation states

| State | Operator visibility | Code behavior |
|-------|---------------------|---------------|
| **Active** | Documented in QUICKSTART / env example | Default or opt-in as documented |
| **Deprecated** | CHANGELOG + log warning on use | Fully functional |
| **Sunset** | Runbook + release notes | Functional; warning escalated |
| **Removed** | Major version only | Gone or hard error with migration link |

## Warning phases

1. **Announce** — CHANGELOG `[Deprecated]` + docs cross-link.
2. **Warn** — Structured log or CLI stderr (one line per process start max).
3. **Sunset window** — Minimum **one minor release** or **90 days** (whichever longer) for operator-facing surfaces.
4. **Remove** — Major version only, with ADR.

## Removal policy

- **Zero silent removals** of CLI commands, Makefile targets, or runtime artifact names in patch/minor.
- Removal requires: ADR, contract test deletion/update, migration section in [migration_safety.md](migration_safety.md).

## Migration grace periods

| Surface | Grace |
|---------|-------|
| Opt-in env flag rename | Alias old name for 1 minor; document both |
| Makefile target rename | Old target prints redirect message 1 minor |
| Inspection JSON field | Keep readable; ignore on read if removed at major |

## Opt-in experimental lifecycle

1. `experimental` in [feature_flag_governance.md](feature_flag_governance.md)
2. Default **off**
3. Promote to `stable` after chaos + soak validation on branch
4. Never default-on in patch release

## Legacy support rules

- **v1.0.x line:** security + bugfix + docs; no new frozen artifacts.
- Legacy retry order (`WORKER_RETRY_SAFE=0`) supported indefinitely until major; documented as less safe.
- Legacy Redis publish fallback supported when `PUBLISH_LOCK_STRICT=0`.

## Migration guidance mandatory

Every deprecation MUST link to:

- Replacement (if any)
- Runbook under `docs/runbooks/upgrades/`
- Rollback step

## Related

- [compatibility_policy.md](compatibility_policy.md) · [release_governance.md](release_governance.md)
