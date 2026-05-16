# v3.2 operational tooling — release publication

**Release type:** Stewardship baseline (offline tooling only)  
**Tag:** `v3.2-operational-tooling-freeze`  
**Program:** ADR-030 through ADR-034

## Release scope

This release **does not** change production-lite runtime execution. It finalizes:

| Phase | Deliverable |
|-------|-------------|
| P3 | Schema governance, validation toolkit, reproducible bundles, static HTML reports |
| P4 | Release kits, ops index, maintenance policy, recovery drill |
| FINAL | Stewardship docs, normalization, immutable baseline, maintainers guide |

## Frozen guarantees

1. **Runtime isolation** — no publisher, worker, scheduler, lock, or frozen contract changes in this release.
2. **Offline tooling** — snapshots → analytics → validation → bundle → kit without network.
3. **Determinism** — CI uses `OPS_FROZEN_UTC`; manifests and checksums on exports.
4. **Bounded storage** — rotation, archive caps, 30MB kit/bundle limits.
5. **Governance** — changes after tag require ADR exception process.

## Operational boundaries

| In scope | Out of scope |
|----------|--------------|
| `var/ops_*` artifacts | Live dashboards |
| Read-only diagnostics embed | Telemetry pipelines |
| Static HTML/SVG reports | Auto-remediation |
| Operator runbooks | Runtime hooks |

## Stewardship expectations

- Run `make stewardship-validate` on any tooling PR.
- Quarterly offline recovery drill sign-off.
- Weekly snapshot cadence (recommended 4h).
- See [MAINTAINERS_GUIDE.md](../MAINTAINERS_GUIDE.md).

## Validation inventory

| Target | Purpose |
|--------|---------|
| `make ops-tooling-validate` | P1 |
| `make ops-analytics-validate` | P2 |
| `make ops-bundle-validate` | P3 |
| `make ops-release-validate` | P4 + integration |
| `make stewardship-validate` | FINAL gate |
| `make ci-test` | Runtime/smoke/contracts |
| `make governance-validate` | Governance contracts |

## Tag and commit references

Recorded in [v3_2_freeze_validation.md](v3_2_freeze_validation.md) after publication.

Prior tooling commits:

| Phase | Commit |
|-------|--------|
| P1 | `876e1b9` |
| P2 | `963bdf0` |
| P3–FINAL closure | *(see freeze validation doc)* |

## Recovery certification

[offline_recovery_certification.md](offline_recovery_certification.md) — engineering certified 2026-05-16 via `make stewardship-validate`.

## Explicit non-goals

- Monitoring platform / APM
- SaaS ops infrastructure
- Runtime observability coupling
- Autonomous publish/retry control
- Multi-tenant ops UI

## Related documents

- [v3_2_immutable_baseline.md](v3_2_immutable_baseline.md)
- [v3_2_transition_notice.md](v3_2_transition_notice.md)
- [v3_2_final_manifest.md](v3_2_final_manifest.md)
