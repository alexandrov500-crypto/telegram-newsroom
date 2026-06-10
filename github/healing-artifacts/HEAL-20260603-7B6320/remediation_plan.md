# Remediation Plan `RP-20260603-AE190A`

**Incident:** `INC-20260603-AEA028`  
**Analysis:** `FA-20260603-698604`  
**Failure type:** `clustering_drift`  
**Confidence:** 0.98  

## Root cause

Critical risk active: RISK-007 — Dual-write schema drift during M2

## Steps

1. Validate STORY_CLUSTER_PERSIST_ENABLED shadow metrics
2. Add cluster persistence integration test
3. Compare cluster snapshot hashes pre/post publish
4. Run dual-write parity report and align ContentPackage field mapping
5. Add publication_record consistency regression test before M2 gate
6. Add cluster persistence integration test

## Impacted ADR-037 issues

- `P1-E04-02`
- `P1-E01-08`
- `P1-E01-07`

## Config changes (advisory — not auto-applied)

- `STORY_CLUSTER_PERSIST_ENABLED`: verify shadow mode before enable
- `CONTENT_PACKAGE_DUAL_WRITE`: Run dual-write parity report and align ContentPackage field mapping
- `PUBLICATION_RECORD_DUAL_WRITE`: Add publication_record consistency regression test before M2 gate
- `STORY_CLUSTER_PERSIST_ENABLED`: Add cluster persistence integration test

## Validation checklist

- [ ] pytest tests/ -k cluster

## Rollback safety (read-only assessment)

Flag remains off in PR; tests only.

## Risk impact

M1 gate sensitive — operator approval mandatory.

---
_Human approval required. No auto-merge, no migration_state changes._
