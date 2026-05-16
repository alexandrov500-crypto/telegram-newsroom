# ADR-036: Immutable stewardship certification

**Status:** Accepted  
**Date:** 2026-05-16  
**Depends on:** ADR-034 (v3.2 finalization), tag `v3.2-operational-tooling-freeze`

## Decision

Establish **archival-grade immutable stewardship certification** for the repository baseline:

- Repository fingerprint manifest
- Immutable archive bundle
- Formal certification and preservation declarations
- `make immutable-baseline-validate` gate

No expansion of tooling capabilities or runtime behavior.

## Immutable baseline philosophy

1. **Tag-bound:** `v3.2-operational-tooling-freeze` is the tooling immutability anchor.
2. **Reproducible:** fingerprints and archives are deterministic under `OPS_FROZEN_UTC`.
3. **Portable:** offline directories with manifests and checksums.
4. **Certifiable:** engineering + governance sign-off documents.
5. **Non-implicit:** no continuation path without governance restart.

## Archival-grade reproducibility expectations

- Sorted JSON inventories with SHA-256 per file
- Git lineage captured when available; SKIP otherwise without failing certification
- Bundle size caps (fingerprint 512KB, archive 10MB)
- Fixture-based integration tests in CI

## Stewardship permanence model

| Layer | State |
|-------|-------|
| Runtime execution | Frozen (separate governance) |
| Ops tooling | Frozen at v3.2 tag |
| Stewardship process | Active, bounded maintenance only |
| Platform evolution | Prohibited without ADR-037+ restart |

## Governance restart requirements

New capabilities require:

1. Written ADR (037+) with non-goals review
2. Updated certification and fingerprint inventories
3. `make immutable-baseline-validate` green
4. Explicit operator + governance sign-off

## Anti-regression guarantees

- `check_freeze_integrity.py` on runtime watch paths
- Drift policy escalation
- Forbidden path and import scans
- Preservation audit quarterly

## Certification boundaries

| In certification scope | Out of scope |
|------------------------|--------------|
| Offline ops tooling | Live Telegram load |
| Governance doc chain | Runtime feature releases |
| Validation Makefile targets | External SaaS ops |

## Allowed

- Bounded stewardship maintenance
- Reproducibility verification
- Archival validation
- Governance-preserving hotfixes

## Forbidden

- Runtime evolution via tooling PRs
- Tooling platformization
- Operational automation growth
- Observability scope expansion
- Hidden governance bypass (undocumented Makefile targets, shadow daemons)

## CI

- `make immutable-baseline-validate`

## References

- [immutable_repository_certification.md](../releases/immutable_repository_certification.md)
- [stewardship_preservation_declaration.md](../releases/stewardship_preservation_declaration.md)
- [governance_preservation_audit.md](../governance/governance_preservation_audit.md)
