# Long-term stewardship (v3.2+)

Guide for maintaining the **offline operational tooling** program after v3.2 FINAL. Does not replace [MAINTENANCE_MODE.md](../MAINTENANCE_MODE.md) for the core application.

## Stewardship responsibilities

| Role | Responsibility |
|------|----------------|
| Operator on-call | Snapshot cadence, weekly kit export, quarterly recovery drill sign-off |
| Engineering | Tooling bugfixes, schema-compatible changes, CI gates |
| Release manager | Stewardship tag discipline, freeze exceptions |

## Cadences

| Activity | Cadence | Command / doc |
|----------|---------|-----------------|
| Metrics snapshot | Every 4h (recommended) | `tools/ops_metrics_snapshot.py --rotate` |
| Analytics refresh | Daily or pre-shift | `ops_analytics_aggregate.py`, `ops_visualize.py` |
| Schema validation | Weekly | `validate_ops_schema.py` |
| Release kit | Weekly / pre-incident | `build_ops_release_kit.py` |
| Archive rotation | Weekly | `ops_archive.py` |
| Archive verification | Monthly | `ops_archive.py --verify-only` |
| Reproducibility gate | Every tooling PR | `make stewardship-validate` |
| Operational audit | Quarterly | [operational_integrity_audit.md](../operations/operational_integrity_audit.md) |
| Offline recovery drill | Quarterly | [offline_ops_recovery_drill.md](../runbooks/offline_ops_recovery_drill.md) |
| Certification refresh | After tooling release | [offline_recovery_certification.md](../releases/offline_recovery_certification.md) |

## Release cadence (tooling)

- **Patch:** bugfix + tests; no schema bump.
- **Minor:** additive schema fields; ADR note; re-run certification.
- **Major:** new ADR cycle required; not expected under v3.2 freeze.

Application releases (v1.x / production-lite) follow [RELEASE_PROCESS.md](../RELEASE_PROCESS.md) separately.

## Acceptable change scope

- Read-only tools and offline `var/` artifacts only
- Deterministic JSON/SVG/HTML outputs
- Documentation and runbook updates
- Test fixture updates with frozen timestamps

## Freeze escalation rules

1. Document proposed change and ADR reference.
2. Run `make stewardship-validate`.
3. Operator + engineering review per [operational_tooling_maintenance_policy.md](operational_tooling_maintenance_policy.md).
4. Update freeze exception log in PR description.
5. If runtime touched → **reject** or split into separate approved runtime PR.

## When NOT to build more tooling

Stop and escalate if someone proposes:

- “Just a small dashboard” — use static HTML index + release kit instead
- “Stream metrics to …” — forbidden; snapshots remain file-based
- “Auto-retry when analytics spike” — forbidden feedback loop
- “Central ops database” — violates bounded `var/` model
- “Hook into publisher for tracing” — runtime coupling
- “Weekly new chart types” — prefer regenerating SVG from existing counters

**Rule of thumb:** if it needs a daemon, database, or live network to **operate**, it is out of scope.

## Verification

```bash
make stewardship-validate
```

## References

- [ADR-034](architecture/ADR-034-v3-2-finalization-and-stewardship.md)
- [v3_2_final_manifest.md](../releases/v3_2_final_manifest.md)
