# v3.2 publication manifest

Canonical inventory for **immutable archival publication** of the v3.2 stewardship baseline.

## Release tags

| Tag | Points to | Purpose |
|-----|-----------|---------|
| `v3.2-operational-tooling-freeze` | `ab7c92aff352ee83619c27f870401bd456ce34c0` | Tooling immutability anchor |
| `v3.2-archival-baseline` | `0e134a2` | Archival publication seal |
| `v3.2-governance-dormant` *(optional)* | post-sealing HEAD | Terminal governance + dormancy seal (recommended after sealing pass) |

## Commit lineage (tooling program)

| Commit | Description |
|--------|-------------|
| `876e1b9` | P1 read-only operational tooling (ADR-030) |
| `963bdf0` | P2 offline analytics (ADR-031) |
| `ab7c92a` | P3–FINAL stewardship baseline |
| `556aedb` | Freeze validation record (docs) |
| `0e23344` | Freeze validation note (docs) |
| `0e134a2` | Archival closure and terminal repository state |

## Canonical entry points

| Path | Role |
|------|------|
| [docs/START_HERE.md](../START_HERE.md) | Onboarding hub |
| [docs/MAINTAINERS_GUIDE.md](../MAINTAINERS_GUIDE.md) | Steward maintenance |
| [docs/releases/repository_terminal_state.md](repository_terminal_state.md) | Terminal state |
| [docs/releases/repository_preservation_notice.md](repository_preservation_notice.md) | DORMANT reader entry |
| [docs/releases/terminal_governance_closure.md](terminal_governance_closure.md) | Governance lifecycle closed |
| [docs/releases/immutable_repository_certification.md](immutable_repository_certification.md) | Certification |

## Validation targets

| Make target | Layer |
|-------------|-------|
| `ops-tooling-validate` | P1 |
| `ops-analytics-validate` | P2 |
| `ops-bundle-validate` | P3 |
| `ops-release-validate` | P4 |
| `stewardship-validate` | FINAL |
| `stewardship-audit-validate` | Post-freeze |
| `immutable-baseline-validate` | Archival |
| `archival-freeze-validate` | Terminal seal |

## Governance manifests

| Document |
|----------|
| [v3_2_final_manifest.md](v3_2_final_manifest.md) |
| [v3_2_immutable_baseline.md](v3_2_immutable_baseline.md) |
| [governance_preservation_audit.md](../governance/governance_preservation_audit.md) |
| [final_repository_preservation_audit.md](../governance/final_repository_preservation_audit.md) |
| [terminal_preservation_sealing_report.md](terminal_preservation_sealing_report.md) |
| [final_dormancy_declaration.md](final_dormancy_declaration.md) |
| [dormancy_transition_verification_report.md](dormancy_transition_verification_report.md) |

## Generated artifacts (gitignored)

| Path | Generator |
|------|-----------|
| `var/stewardship_integrity/repository_fingerprint.json` | `build_repository_fingerprint.py` |
| `var/immutable_archive/<YYYYMMDD>/` | `build_immutable_archive_bundle.py` |
| `var/immutable_archive/integrity_seal.json` | `build_archival_integrity_seal.py` |

SHA-256: see `repository_fingerprint.json` → `content_sha256` and archive `checksums.sha256`.

## Operational guarantees

1. Offline read-only tooling — no runtime mutation path
2. Deterministic exports — `OPS_FROZEN_UTC` in CI
3. Bounded storage — retention policy + bundle caps
4. Governance-only evolution — ADR-037+ restart required (denied by default in dormancy)
5. **No future support implied** — preservation-only; see [repository_preservation_notice.md](repository_preservation_notice.md)

## Recovery references

- [offline_ops_recovery_drill.md](../runbooks/offline_ops_recovery_drill.md)
- [offline_recovery_certification.md](offline_recovery_certification.md)

## Archival references

- [v3_2_archival_closure_report.md](v3_2_archival_closure_report.md)
- [stewardship_preservation_declaration.md](stewardship_preservation_declaration.md)
- [ADR-036](../architecture/ADR-036-immutable-stewardship-certification.md)

## Reproducibility expectations

```bash
export OPS_FROZEN_UTC=2026-05-16T12:00:00Z
make archival-freeze-validate
```

Identical fixture inputs → identical manifest file lists and seal structure (modulo `generated_at` / git HEAD in fingerprint).
