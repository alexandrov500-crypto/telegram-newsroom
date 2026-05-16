# Offline recovery certification (v3.2)

Certifies that operational artifacts can be rebuilt **without network, Telegram, or Redis**.

## Certification checklist

| # | Criterion | Verification method | Status |
|---|-----------|---------------------|--------|
| 1 | Snapshots recoverable | Fixture load + `validate_snapshot_file` | ☑ |
| 2 | Archives recoverable | `verify_archive_file` roundtrip test | ☑ |
| 3 | Release kits reproducible | `test_offline_ops_toolchain` double manifest match | ☑ |
| 4 | Reports reproducible | `test_toolchain_reproducibility` | ☑ |
| 5 | Schemas verifiable | `validate_ops_schema.py` + governance contracts | ☑ |
| 6 | Corruption isolated | corrupt fixture → `CORRUPT` status, analytics continues | ☑ |
| 7 | Offline rebuild successful | `make ops-release-validate` end-to-end | ☑ |
| 8 | Deterministic outputs verified | `OPS_FROZEN_UTC=2026-05-16T12:00:00Z` in CI | ☑ |

## Automated verification

```bash
make stewardship-validate
```

Last engineering verification: **2026-05-16** (CI fixture run, frozen UTC).

## Manual drill (operator)

Follow [offline_ops_recovery_drill.md](../runbooks/offline_ops_recovery_drill.md) and sign below.

## Operator sign-off

| Role | Name | Date | Notes |
|------|------|------|-------|
| Operator on-call | | | |
| Engineering | | | |

**Certification:** ☑ ENGINEERING (automated) · ☐ OPERATOR (manual drill pending)
