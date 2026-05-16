# Immutable repository certification

Formal certification of the repository as an **archival-grade immutable stewardship baseline** at v3.2.

**Freeze tag:** `v3.2-operational-tooling-freeze`  
**Freeze commit:** `ab7c92aff352ee83619c27f870401bd456ce34c0`  
**Certification date:** 2026-05-16

## Certification checklist

| # | Criterion | Verification | Status |
|---|-----------|--------------|--------|
| 1 | Runtime freeze integrity | `check_freeze_integrity.py`; no runtime diff since tag | ☑ |
| 2 | Tooling isolation | Ops tools offline; no runtime imports | ☑ |
| 3 | Offline reproducibility | `make stewardship-validate` | ☑ |
| 4 | Deterministic outputs | `OPS_FROZEN_UTC` integration tests | ☑ |
| 5 | Bounded storage lifecycle | Retention policy + bundle caps | ☑ |
| 6 | Governance completeness | ADR-030–036; preservation audit | ☑ |
| 7 | Archival readiness | `build_immutable_archive_bundle.py` | ☑ |
| 8 | Recovery reproducibility | [offline_recovery_certification.md](offline_recovery_certification.md) | ☑ |

## Validation references

```bash
make immutable-baseline-validate
make stewardship-validate
```

Artifacts:

- `var/stewardship_integrity/repository_fingerprint.json`
- `var/immutable_archive/<YYYYMMDD>/manifest.json`

## Freeze references

- [v3_2_immutable_baseline.md](v3_2_immutable_baseline.md)
- [v3_2_freeze_validation.md](v3_2_freeze_validation.md)
- [stewardship_state_declaration.md](stewardship_state_declaration.md)

## Sign-off

| Role | Name | Date |
|------|------|------|
| Engineering | | 2026-05-16 |
| Governance / release manager | | |

**Certification:** ☑ ENGINEERING (automated gates) · ☐ GOVERNANCE (manual)
