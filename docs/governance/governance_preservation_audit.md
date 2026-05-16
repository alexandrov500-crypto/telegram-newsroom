# Governance preservation audit

Quarterly review ensuring **v3.2 stewardship governance** remains intact and enforceable.

## Audit scope

| Area | Check |
|------|-------|
| ADR chain continuity | ADR-030 → ADR-036 present; no contradictory ADRs |
| Freeze policy consistency | `v3_2_tooling_freeze` aligns with ADR-034/036 |
| Stewardship boundaries | State + preservation declarations current |
| Validation chain | Makefile targets documented and tested |
| Archival sustainability | Fingerprint + immutable archive caps respected |
| Maintenance sustainability | Hotfix procedure followed on recent PRs |
| Anti-platform-creep | No new daemons, telemetry, dashboards |

## Governance erosion indicators

| Indicator | Severity |
|-----------|----------|
| Runtime files in tooling PR | S1 |
| New ops tool without ADR | S2 |
| Missing `immutable-baseline-validate` on tooling PR | S2 |
| Undocumented `var/` directory | S3 |
| Broken START_HERE / MAINTAINERS links | S3 |
| Moved or deleted freeze tag | S1 |

## Escalation criteria

- **S1:** Stop merge; engineering lead + governance review within 24h
- **S2:** Block until ADR note or validation restored
- **S3:** Docs fix in next maintenance window

## Preservation guarantees

1. Tag `v3.2-operational-tooling-freeze` remains immutable reference.
2. Certification documents are version-controlled, not generated-only.
3. CI gates cannot be removed without governance sign-off.
4. Fingerprint inventory lists all stewardship tools explicitly.

## Verification commands

```bash
make immutable-baseline-validate
python3 tools/build_repository_fingerprint.py
```

## Sign-off

| Quarter | Reviewer | Date | Pass |
|---------|----------|------|------|
| 2026-Q2 | | | ☐ |
