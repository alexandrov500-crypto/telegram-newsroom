# Operational tooling maintenance policy (v3.2)

Governs the **offline ops tooling stack** (ADR-030–033). Does not govern production-lite runtime or frozen `runtime/*.json` contracts.

## Ownership expectations

| Role | Responsibility |
|------|----------------|
| Operator on-call | Snapshot cadence, kit export before/after incidents, sign-off on integrity audit |
| Engineering | Schema changes, tool fixes, CI gates, ADR updates |
| Release manager | Tooling freeze approval per [v3_2_tooling_freeze.md](../releases/v3_2_tooling_freeze.md) |

## Cadences

| Activity | Cadence |
|----------|---------|
| Ops snapshot capture | Every 4h (recommended) |
| Schema review | Each tooling PR touching `utils/ops_*` |
| Archive cleanup | Weekly `ops_archive.py` |
| Reproducibility verification | Every PR: `make ops-release-validate` |
| Release kit export | Weekly or pre-shift |
| Integrity audit doc | Quarterly or post-incident |

## Acceptable operational debt

- Stale SVG reports (regenerate anytime)
- Empty `var/ops_history/` on new hosts until first snapshot
- WARN on legacy diagnostics without `schema_version`
- Manual index regeneration after kit export

**Not acceptable:** corrupt snapshots without validation run; kit checksum failures; unbounded `var/` growth without rotation.

## Freeze escalation process

1. File issue with `tooling-freeze` label and ADR reference.
2. Run `make ops-release-validate` on branch.
3. Engineering + operator review maintenance policy checklist.
4. Update [v3_2_tooling_freeze.md](../releases/v3_2_tooling_freeze.md) sign-off.
5. Tag: `v3.2-operational-tooling-freeze` (see [v3_2_stewardship_handoff.md](../releases/v3_2_stewardship_handoff.md)).

## Tooling change approval matrix

| Change type | Approval | CI gate |
|-------------|----------|---------|
| Doc-only runbook | 1 engineer | `ops-tooling-validate` |
| New read-only tool | 1 engineer + operator ack | `ops-release-validate` |
| Schema minor (additive) | ADR note + engineer | `ops-bundle-validate` |
| Schema major | ADR + freeze review | Full `ci-test` |
| Runtime / publish touch | **Rejected** | N/A |

## Forbidden change classes

- Importing `publisher`, `worker`, or live Telegram clients from ops tools (except existing read-only diagnostics collector)
- Network calls in ops validation/export paths
- Background daemons or scheduled in-repo services
- Writing to `runtime/` or mutating frozen contracts
- Expanding kit size limits without ADR

## Emergency hotfix rules

1. Fix must remain read-only and offline.
2. Add regression test in `tests/tools` or `tests/integration`.
3. Run `make ops-release-validate` before merge.
4. Post-incident: update recovery drill if steps changed.
5. No runtime hotfix bundled in same PR unless explicitly scoped and approved separately.

## Verification commands

```bash
make ops-tooling-validate
make ops-analytics-validate
make ops-bundle-validate
make ops-release-validate
```
