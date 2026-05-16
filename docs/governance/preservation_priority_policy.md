# Preservation priority policy

Normative ordering for all decisions after v3.2 archival baseline. **Higher priority wins conflicts.**

## Priority order

| Rank | Principle | Meaning |
|------|-----------|---------|
| 1 | **Archival integrity** | Tags, manifests, seals, lineage immutable |
| 2 | **Governance continuity** | ADR chain, review records, certification docs |
| 3 | **Runtime stability** | Production-lite execution unchanged by tooling |
| 4 | **Reproducibility** | Deterministic exports and CI fixtures |
| 5 | **Operational simplicity** | Shell-first, offline, no control plane |
| 6 | **Bounded maintenance** | Hotfixes within [maintenance_hotfix_procedure.md](../runbooks/maintenance_hotfix_procedure.md) |
| 7 | **New evolution** | Only after ADR-037 restart process approves a **new program** |

## Anti-platform-creep doctrine

**Platform creep** = introducing hosted services, persistent ops databases, live dashboards, streaming telemetry, or autonomous control loops.

**Rule:** If it needs a daemon, always-on network listener, or SaaS account for **operations**, it violates rank 1–5 unless restart program explicitly redefines scope with new ADRs.

## Anti-scope-accumulation doctrine

**Scope accumulation** = “just one more” tool, chart, integration, or Makefile target without governance restart.

**Rule:** Each additive capability requires either:

- Classification as **bounded hotfix** (rank 6), or
- Completed **restart evaluation** (rank 7)

No third path.

## Simplicity preservation rules

1. Prefer regenerating `var/` artifacts over new storage locations.
2. Prefer static HTML/SVG over interactive UI.
3. Prefer one Makefile gate over many overlapping gates.
4. Prefer documenting “how to run existing tools” over writing new tools.
5. Prefer rejecting proposals to extending validation chains without restart approval.

## Conflict resolution

When ranks conflict:

- Document the conflict in writing.
- Escalate to governance review ([governance_restart_review.md](../runbooks/governance_restart_review.md)).
- **Default:** preserve higher rank (lower number).

## References

- [ADR-037](../architecture/ADR-037-governance-restart-framework.md)
- [terminal_state_preservation_addendum.md](../releases/terminal_state_preservation_addendum.md)
