# Controlled sunset scenarios

Graceful aging paths — **not** shutdown automation or abandonment.

## Scenario matrix

| Scenario | Survivability expectation | Operator expectation | Recovery confidence | Unsupported assumption |
|----------|---------------------------|--------------------|---------------------|------------------------|
| **Active development slows** | High | Same runbooks; fewer releases | High at last tag | `main` always installable without test |
| **Maintenance-only period** | High | CVE + critical fixes only | High if tags preserved | Monthly feature delivery |
| **No new releases for years** | Medium–High | Recover from **tag** + archive | Medium without drill | `pip install` on old pins forever |
| **Maintainer transition** | Medium | Read stewardship + legacy docs | High if git+ADR intact | Oral handoff only |
| **Ecosystem drift** | Medium | Uplift branch when EOL | Medium after uplift work | Zero-change external APIs |
| **Final stewardship handoff** | Medium | Archive bundle + this doc set | High with complete archive | Incomplete OUTPUT_DIR “OK” |

## Active development slows

- Freeze scope expansion; maintenance-first ([MAINTENANCE_MODE.md](../MAINTENANCE_MODE.md)).
- Last green tag becomes reference legacy baseline.

## Maintenance-only period

- Accept: PATCH pins, doc fixes, runbook clarifications.
- Reject: new frozen artifacts, default-on flags, platform initiatives.

## No new releases for years

- **Supported:** Run last tag; archive sqlite + OUTPUT_DIR + env template.
- **Unsupported:** Claim `main` HEAD works on future Python without uplift.

## Maintainer transition

Handoff package:

1. [adr_lineage_map.md](../stewardship/adr_lineage_map.md)
2. [legacy_state_definition.md](legacy_state_definition.md)
3. Last stable tag name
4. `make legacy-validate` output (saved JSON optional)

## Ecosystem drift

- Follow [ecosystem_aging.md](../preservation/ecosystem_aging.md).
- Sunset of Python → uplift, not emergency rewrite.

## Final stewardship handoff

- No “archive-only” repo conversion in-tree.
- Operator retains backups; repo retains **how to recover**.
- Optional: mark repo status in README (maintainer choice, not automated).

## What sunset is NOT

- Automated decommission
- Deleting ADRs or reports
- Forced migration to Postgres/K8s
- Declaring project dead without recovery path
