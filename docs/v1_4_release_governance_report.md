# v1.4 release governance report

**Branch:** `v1.4-release-governance`  
**Scope:** Documentation + read-only readiness tooling — no runtime contract changes

---

## Compatibility guarantees

| Surface | Guarantee |
|---------|-----------|
| 14 runtime JSON artifacts | Frozen (names, lifecycle, schema v1) |
| 11 inspection CLIs | Frozen registry |
| Evidence snapshots | Directory of frozen filenames; portable across 1.x patch |
| Opt-in flags | Default off; backward compatible |
| Tool JSON reports | Separate schema_version; not part of 14-artifact freeze |

Formal policy: [compatibility_policy.md](compatibility_policy.md)

---

## Supported upgrade paths

- **Patch:** `v1.0.x` → `v1.0.y` — `make release-check`
- **Minor:** opt-in features + validation — `make resilience-validate` + `release_readiness.py --strict`
- **Rollback:** Class A–D in [migration_safety.md](migration_safety.md)

---

## Migration safety assessment

- L0–L3 risk table defined
- Snapshot-before-change mandatory for L1+
- SQLite precheck runbook for app migrations
- No automated migration daemon (by design)

---

## Release governance maturity

| Capability | Status |
|------------|--------|
| Release classes (patch/minor/operational/experimental) | Documented |
| Gate matrix | [release_governance.md](release_governance.md) |
| Deprecation lifecycle | [deprecation_policy.md](deprecation_policy.md) |
| Readiness validator | `tools/release_readiness.py` (read-only) |
| Maintenance cadence | [maintenance_matrix.md](maintenance_matrix.md) |

**Grade: A (production-lite governance)** — lean process, deterministic gates, no enterprise theater.

---

## Evidence lifecycle stability

- Retention/prune tooling referenced (`evidence_retention`, `runtime_retention`)
- Manifest checksum authority unchanged
- Additive JSON only in 1.x

---

## Feature flag governance status

- Four reliability/diagnostic flags registered
- Incompatible combo warnings in readiness tool (`--check-env`)
- Promotion rules documented

---

## Long-term maintenance readiness

- Daily / weekly / monthly / per-release matrix
- Chaos + soak cadence linked
- Upgrade runbooks under `docs/runbooks/upgrades/`

---

## Remaining governance risks

- Operator may skip backup before minor upgrade
- Env flag drift undetected without `RUNTIME_DRIFT_MONITOR`
- Major version (v2) process not yet exercised
- No signed release artifacts in-repo (operator responsibility)

---

## Recommended v1.5 priorities

1. Signed release checklist (optional GPG/SBOM doc-only)
2. Automated `release_readiness.py` in CI on release branches
3. Drift baseline store format versioning (tooling only)
4. PostgreSQL operational path doc (still opt-in, no forced migration)
5. Consolidated operator PDF/quickref (optional)

---

## Validation

```bash
make ci-test
make release-check
make chaos-test
make resilience-validate
make governance-validate
python3 tools/release_readiness.py --strict
```
