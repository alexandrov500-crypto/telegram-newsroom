# Operational durability audit

Long-term sustainability of **operations**, not feature count.

## Long-term operator burden

| Area | Durability | Notes |
|------|------------|-------|
| Daily ops | High | Makefile + OPERATOR_QUICKSTART |
| Incident response | High | Runbooks + semantics forbidden states |
| Rare releases | Medium | release-check gate |
| Dependency CVEs | Medium | security-validate; manual pin bumps |
| Dormancy return | Medium | ecosystem_continuity + this doc set |

**Risk:** Makefile target proliferation — LOW hint in architecture guardrails.

## Maintenance sustainability

- **Minimal viable maintenance** ([maintainer_longevity.md](../architecture/maintainer_longevity.md)): monthly security, quarterly traceability, annual recovery drill.
- Frozen contracts reduce “surprise work” during dormancy.

## Recovery durability

- 12-artifact model + validate-recovery unchanged for years if schema v1 holds.
- Long-horizon paths: [long_horizon_recovery.md](long_horizon_recovery.md).

## Governance durability

- SSOT docs: compatibility_policy, feature_flag_governance, semantics, preservation.
- `make governance-validate` — release readiness without external SaaS.

## ADR readability durability

- [adr_lineage_map.md](../stewardship/adr_lineage_map.md) + archaeology index.
- ADRs not deleted — superseded only.

## Runbook survivability

- Scaling/security/runbooks use stable headers (Detection, Mitigation).
- Link to semantics matrix instead of duplicating guarantees.

## Tooling discoverability durability

| Tool family | Role |
|-------------|------|
| `*_guardrails.py` | Read-only stewardship |
| `release_readiness.py` | Pre-tag |
| `ops_summary.py` | Operator dashboard CLI |

`make docs-map` lists phase reports.

## Durability grade (informal)

| Dimension | Grade |
|-----------|-------|
| Inspection evidence | A |
| Written governance | A |
| External API dependence | C+ (inherent) |
| Dependency pins | B+ (maintainer discipline) |

Overall **operationally durable** for production-lite scope — not hyperscale SLA durable.
