# Upgrade runbooks

Operator-safe upgrade paths. See [compatibility_policy.md](../../compatibility_policy.md) and [release_governance.md](../../release_governance.md).

| Runbook | Use when |
|---------|----------|
| [PATCH_UPGRADE.md](PATCH_UPGRADE.md) | `v1.0.x` → `v1.0.y` |
| [MINOR_UPGRADE.md](MINOR_UPGRADE.md) | New minor with opt-in flags |
| [SAFE_ROLLBACK.md](SAFE_ROLLBACK.md) | Revert after failed upgrade |
| [EXPERIMENTAL_FLAG_ENABLE.md](EXPERIMENTAL_FLAG_ENABLE.md) | Enable reliability flags on staging |
| [SQLITE_MIGRATION_PRECHECK.md](SQLITE_MIGRATION_PRECHECK.md) | Before app DB migrations |
