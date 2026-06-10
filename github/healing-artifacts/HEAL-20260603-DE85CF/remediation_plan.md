# Remediation Plan `RP-20260603-B09836`

**Incident:** `INC-20260603-AEA028`  
**Analysis:** `FA-20260603-D0E90B`  
**Failure type:** `dual_write_inconsistency`  
**Confidence:** 0.98  

## Root cause

Critical risk active: RISK-007 — Dual-write schema drift during M2

## Steps

1. Run dual-write reconciliation report on staging
2. Align PublicationRecord field mapping with ContentPackage schema
3. Add consistency checker with fail-soft logging
4. Run dual-write parity report and align ContentPackage field mapping
5. Add publication_record consistency regression test before M2 gate
6. Add cluster persistence integration test

## Impacted ADR-037 issues

- `P1-E04-02`
- `P1-E01-08`
- `P1-E01-07`

## Config changes (advisory — not auto-applied)

- `PUBLICATION_RECORD_DUAL_WRITE`: do not enable until parity checklist passes
- `CONTENT_PACKAGE_DUAL_WRITE`: Run dual-write parity report and align ContentPackage field mapping
- `PUBLICATION_RECORD_DUAL_WRITE`: Add publication_record consistency regression test before M2 gate
- `STORY_CLUSTER_PERSIST_ENABLED`: Add cluster persistence integration test

## Validation checklist

- [ ] pytest tests/ -k dual_write or publication_record
- [ ] python scripts/evaluate_gate.py --gate M1_TO_M2

## Rollback safety (read-only assessment)

PR excludes migration_state.txt and production env changes.

## Risk impact

HIGH — dual-write path; draft PR for review only.

---
_Human approval required. No auto-merge, no migration_state changes._
