# v3.2 P3 exit criteria

Operational schema governance and release hardening complete when all criteria below are satisfied.

## Deliverables

| Item | Status |
|------|--------|
| ADR-032 | ☑ |
| `validate_ops_schema.py` | ☑ |
| `export_ops_bundle.py` | ☑ |
| `generate_ops_html_report.py` | ☑ |
| `operational_integrity_audit.md` | ☑ |
| `make ops-bundle-validate` | ☑ |

## Quality gates

| # | Criterion | Verification | Met |
|---|-----------|--------------|-----|
| 1 | Schemas governed and versioned | ADR-032; contract tests | ☑ |
| 2 | Exports reproducible | `test_toolchain_reproducibility.py` | ☑ |
| 3 | Reports portable/offline | single-file HTML, embedded SVG | ☑ |
| 4 | Archives verifiable | `verify_archive_file` in validation | ☑ |
| 5 | Corruption isolated safely | corrupt fixture tests | ☑ |
| 6 | Deterministic tooling confirmed | frozen `OPS_FROZEN_UTC` in CI | ☑ |
| 7 | Operational audits documented | integrity audit checklist | ☑ |
| 8 | Production-lite runtime untouched | no publisher/worker/contract edits | ☑ |

## Validation

```bash
make ops-bundle-validate
make ops-analytics-validate
make ops-tooling-validate
make ci-test
```

## Sign-off

| Role | Date |
|------|------|
| Operator | |
| Engineering | |

**P3 status:** ☑ COMPLETE (engineering)
