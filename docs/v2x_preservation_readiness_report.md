# v2.x preservation readiness report

Long-horizon survivability — documentation and read-only guardrails only.

## Preservation Sustainability Grade

| Area | Grade | Notes |
|------|-------|-------|
| Evidence / SQLite archive | A | File-based, schema v1 frozen |
| Written recovery paths | A | long_horizon_recovery.md |
| External APIs | C+ | Telegram/OpenAI inherent drift |
| Dependency pins | B+ | Discipline-dependent |
| Dormancy playbook | A | ecosystem_continuity + preservation |

**Overall:** Preservation-ready for production-lite scope with operator discipline.

## Ecosystem Survivability Assessment

See [ecosystem_aging.md](preservation/ecosystem_aging.md):

- SQLite: strongest asset
- Telethon/aiogram/OpenAI: watch items
- Redis: optional for minimal profile
- Python: uplift on EOL schedule

## Long-Horizon Recovery Status

[long_horizon_recovery.md](preservation/long_horizon_recovery.md) documents 5-year, dependency drift, Python EOL, API change, maintainer gap, and archival-only paths with difficulty ratings.

## Dependency Aging Risk Assessment

[dependency_preservation.md](preservation/dependency_preservation.md) — critical vs optional, pin policy, no aggressive modernization.

## Operational Durability Grade

[operational_durability.md](preservation/operational_durability.md) — informal A/B grades on inspection and governance durability.

## Remaining Long-Term Risks

| Risk | Mitigation |
|------|------------|
| Telegram/OpenAI breaking change | Pin + phased uplift |
| Operator archive incomplete | minimal_survivable_profile checklist |
| Dormancy + stale main branch | Recover from **tag** |
| False confidence from old reports | Reports are validation snapshots, not SLA |

## Recommended Preservation Stewardship Model

**Multi-year low-activity:**

| When | Action |
|------|--------|
| Monthly | `security-validate` (CVE pins) |
| Quarterly | `preservation-validate`, `traceability-validate` |
| Annual | Recovery drill + dependency pin review |
| On return | START_HERE → post-dormancy → enable flags one-by-one |

No vendoring; no archive appliance; no rewrite.

## Preservation Readiness Assessment

Preservation = **documented recoverability** + **pinned deps** + **frozen inspection contracts** + guardrails — not offline mirror of PyPI.

## Ecosystem Aging Outlook

Documented per component with replacement difficulty and horizons.

## Long-Horizon Recovery Confidence

High for inspection-only T3 from complete OUTPUT_DIR + sqlite.

Medium for live editorial after 5 years without tag-locked reinstall.

Low for unsupported multi-region / exactly-once claims.

## Dependency Survivability Status

Critical runtime deps pinned in requirements.txt; optional `>=` on redis/asyncpg documented.

## Operational Durability Assessment

Makefile + runbooks + guardrails family remain discoverable via START_HERE and docs-map.

## Remaining Preservation Risks

See table above; no new runtime mitigations in this phase (by design).

## Recommended Multi-Year Stewardship Strategy

1. Tag releases; archive tag name with backups
2. Never delete ADRs; update preservation docs on Python floor change
3. `make preservation-validate` before rare tags
4. Stay 1.x until v2 gates fire ([v2_transition_strategy.md](architecture/v2_transition_strategy.md))

## Validation

```bash
make preservation-validate
make ci-test
make governance-validate
make architecture-validate
```

## Backward compatibility

- No runtime contract changes
- No ecosystem rewrite
- No vendoring
- Read-only tooling
