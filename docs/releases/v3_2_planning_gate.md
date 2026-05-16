# v3.2 planning gate

v3.2 **planning** (docs, ADRs, read-only tooling designs) may proceed only when all exit criteria below are satisfied. **Implementation** of runtime-affecting items requires separate ADR per item + end of stabilization freeze.

## Gate criteria

| # | Criterion | Evidence | Met |
|---|-----------|----------|-----|
| 1 | 72h stable runtime | [72h_operational_findings.md](../operations/72h_operational_findings.md) conclusions | ☐ |
| 2 | No critical incidents in window | Postmortem log empty or closed | ☐ |
| 3 | Rollback verified | `DRY_RUN` drill documented <30d | ☐ |
| 4 | Operator workflow sustainable | 72h findings + governance audit | ☐ |
| 5 | Metrics baselines collected | [production_baselines.md](../operations/production_baselines.md) filled | ☐ |
| 6 | Diagnostics trusted | No unresolved false-positive pattern | ☐ |
| 7 | Governance functioning | [production_governance_audit.md](../governance/production_governance_audit.md) COMPLIANT | ☐ |
| 8 | No unresolved production-lite instability | No open HIGH findings | ☐ |

**Gate status:** ☐ OPEN (v3.2 planning allowed) ☐ CLOSED

## Authorized v3.2 outputs (when OPEN)

- [v3_2_discovery.md](../architecture/v3_2_discovery.md) → ADR-030 draft (scope)
- Read-only tooling RFCs
- Technical debt registry updates
- No merge to production without freeze policy check

## Blocked until gate OPEN

- Retry model changes
- Publish pipeline changes
- Runtime contract changes
- Default-on observability servers
- Multi-worker scheduler

## Sign-off

| Role | Name | Date |
|------|------|------|
| Operator owner | | |
| Engineering | | |

## After gate

1. Prioritize P1 from discovery (ops tooling)
2. Schedule ADR reviews
3. Keep production branch stable-first; use feature branch per tool
