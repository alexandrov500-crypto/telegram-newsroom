# Governance restart evaluation template

**Use when:** proposing to open a post-v3.2 implementation or governance program.  
**Default answer:** do not restart. Complete this template before any ADR-038+ draft.

**Proposal ID:** _______________  
**Author:** _______________  
**Date:** _______________  
**Status:** Draft | Under review | Rejected | Deferred

---

## 1. Problem statement

Describe the **observed operational failure** (not desired feature):

- What fails today?
- Who is affected (operator / engineering)?
- Since when? Frequency?

---

## 2. Why v3.2 is insufficient

Reference specific gaps:

- [ ] Archival baseline (`v3.2-archival-baseline`)
- [ ] Tooling freeze (`v3.2-operational-tooling-freeze`)
- [ ] Stewardship hotfix path ([maintenance_hotfix_procedure.md](../runbooks/maintenance_hotfix_procedure.md))
- [ ] Recovery drill ([offline_ops_recovery_drill.md](../runbooks/offline_ops_recovery_drill.md))

Explain why each checked item cannot address the problem.

---

## 3. Why maintenance/hotfix is not enough

List hotfix attempts or explain why hotfix scope is exceeded per [preservation_priority_policy.md](preservation_priority_policy.md).

---

## 4. Operational evidence

| Evidence type | Attached | Summary |
|---------------|----------|---------|
| Incident logs | ☐ | |
| Snapshot/kit exports | ☐ | |
| Freeze integrity report | ☐ | |
| External mandate (security) | ☐ | |

**No evidence → automatic rejection.**

---

## 5. Rollback implications

How is rollback guaranteed if restart work fails?

- Runtime rollback path:
- Tooling rollback path:
- Tag/archive preservation:

---

## 6. Governance impact

- New ADRs required (numbers):
- New Makefile targets? (discouraged)
- Changes to frozen tags? (forbidden without new tag line)

---

## 7. Archival compatibility

How will historical auditability be preserved?

- [ ] `v3.2-operational-tooling-freeze` remains unmoved
- [ ] `v3.2-archival-baseline` remains authoritative for v3.2 era
- [ ] New work uses new tag prefix (e.g. `v4-*`), not retcon

---

## 8. Runtime risk

| Risk | Mitigation |
|------|------------|
| Publish semantics change | |
| Retry/scheduler change | |
| Contract mutation | |

**Any unmitigated runtime risk → reject.**

---

## 9. Scope containment strategy

Maximum allowed scope in one sentence:

Proposed phase boundaries (docs-only first?):

---

## 10. Why NOT restarting is preferable

*Required.* Argue against your own proposal:

1.
2.
3.

---

## 11. What must remain frozen forever

List non-negotiables:

- Runtime contracts (14 artifacts)?
- Tooling freeze tag?
- Archival lineage?

---

## 12. What would invalidate restart

Conditions that abort an approved restart mid-flight:

- Runtime PR without runtime ADR
- Tooling PR without stewardship audit
- Moved/deleted freeze tags
- Undocumented validation targets

---

## Review signatures

| Role | Decision | Date |
|------|----------|------|
| Stewardship | Reject / Defer / Proceed to meta-study | |
| Preservation | Reject / Defer / Proceed | |
| Governance | Reject / Defer / Proceed | |

**Cooling-off:** minimum **30 days** after rejection before resubmission (see [governance_restart_review.md](../runbooks/governance_restart_review.md)).
