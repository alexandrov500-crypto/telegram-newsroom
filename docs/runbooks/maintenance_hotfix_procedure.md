# Maintenance hotfix procedure (v3.2 tooling)

Controlled path for **stewardship-mode** changes. Not for runtime/publish/retry work.

## Allowed hotfixes

| Category | Example |
|----------|---------|
| Deterministic bugfix | corrupt JSON edge case in validator |
| Docs correction | runbook typo, broken link |
| Schema-compatible tooling | additive JSON field + test |
| Archive/recovery | `verify_archive_file` false positive |
| Reproducibility | manifest sort order fix |
| Security | dependency pin (no new network deps) |

## Forbidden (reject PR)

| Category | Reason |
|----------|--------|
| Runtime behavior changes | Separate runtime release + ADR |
| Publish/retry/scheduler/lock edits | Frozen execution path |
| Observability scope expansion | Platform creep |
| Telemetry / streaming additions | Offline-only rule |
| Operational automation | No closed-loop control |
| Hosted dashboards | ADR-034 forbidden |

## Per-hotfix checklist

### 1. Intake

- [ ] Issue describes bug/doc scope only
- [ ] No runtime files in diff (`publisher/`, `collector/`, frozen contracts)
- [ ] Stewardship approval (engineering + operator for operator-facing output)

### 2. Implementation

- [ ] Smallest diff; no drive-by refactors
- [ ] Tests added or updated (fixtures + frozen UTC if needed)
- [ ] `check_freeze_integrity.py` still passes

### 3. Validation

```bash
make stewardship-audit-validate
make stewardship-validate
```

### 4. Rollback plan

- Revert git commit
- Regenerate `var/ops_reports/` if outputs changed
- No application restart required for tooling-only rollback

### 5. Post-fix audit

- [ ] Update CHANGELOG under stewardship/maintenance
- [ ] Note in PR: freeze integrity status
- [ ] No new tag unless release manager requests patch tag (rare)

## Emergency hotfix

1. Branch `hotfix/ops-<short-desc>` per [maintenance_branch_policy.md](../governance/maintenance_branch_policy.md)
2. Fix + tests + `make stewardship-audit-validate`
3. Merge within 24h; full quarterly audit still required

## References

- [drift_detection_policy.md](../governance/drift_detection_policy.md)
- [operational_tooling_maintenance_policy.md](../governance/operational_tooling_maintenance_policy.md)
