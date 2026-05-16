# Repository terminal state declaration

**Effective:** upon archival closure and tag `v3.2-archival-baseline`  
**Prior tooling anchor:** `v3.2-operational-tooling-freeze`

## Terminal state

| Lifecycle | Status |
|-----------|--------|
| v3.2 implementation | **Complete** — closed |
| v3.2 stewardship | **Complete** — closed |
| Archival preservation | **Active** — maintenance-only |
| Governance mode | **Dormant** ([final_dormancy_declaration.md](final_dormancy_declaration.md)) |
| Repository roadmap | **None implicit** |

## Formal statements

1. **Implementation lifecycle is fully complete** for v3.2 operational tooling.
2. **Stewardship lifecycle is fully complete** as an active implementation program.
3. **Archival lifecycle is active** — regeneration, audits, hotfixes within bounds only.
4. The repository is **intentionally terminal/frozen** for scope expansion at v3.2.
5. **No implicit roadmap continuation** exists in Makefile targets or ADRs.
6. **Future changes require explicit reactivation** — [ADR-037](../architecture/ADR-037-governance-restart-framework.md) evaluation only (no implementation by default); see [restart_readiness_declaration.md](restart_readiness_declaration.md).

## Bounded ecosystem (permanent)

- Offline ops snapshots and exports under `var/ops_*`
- Static reports and release kits
- Governance and certification documents in `docs/`

## What remains allowed

See [final_repository_preservation_audit.md](../governance/final_repository_preservation_audit.md) and [maintenance_hotfix_procedure.md](../runbooks/maintenance_hotfix_procedure.md).

## Entry points

- [v3_2_publication_manifest.md](v3_2_publication_manifest.md)
- [MAINTAINERS_GUIDE.md](../MAINTAINERS_GUIDE.md)
- [v3_2_archival_closure_report.md](v3_2_archival_closure_report.md)

## Verification

```bash
make archival-freeze-validate
git describe --tags
```
