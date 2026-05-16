# Repository preservation notice

**To:** operators, engineers, auditors, future maintainers  
**Re:** Telegram newsroom — v3.2 archival repository  
**Date:** 2026-05-16

## Notice

This repository is **preserved intentionally**. **Development is intentionally inactive.** The archival baseline is **authoritative**. Stewardship has **reduced to dormancy mode**. Any future engineering activity is **exceptional by definition** and requires [ADR-037](../architecture/ADR-037-governance-restart-framework.md) process — **no restart is currently approved**.

## Canonical tags

| Tag | Commit (reference) | Role |
|-----|-------------------|------|
| `v3.2-operational-tooling-freeze` | `ab7c92a` | Tooling immutability |
| `v3.2-archival-baseline` | `0e134a2` | Archival publication |
| `v3.2-governance-dormant` *(optional)* | after terminal sealing commit | Governance + dormancy terminal seal |

Do not move or reuse these tags for new work.

## Canonical manifests

| Document | Purpose |
|----------|---------|
| [v3_2_publication_manifest.md](v3_2_publication_manifest.md) | Release inventory |
| [v3_2_final_manifest.md](v3_2_final_manifest.md) | Program inventory |
| [meta_governance_closure.md](meta_governance_closure.md) | Meta-governance closed |
| [terminal_preservation_sealing_report.md](terminal_preservation_sealing_report.md) | Final dormancy sealing record |

## Canonical validation entry points

Run on **tagged checkout** when verifying preservation (not on every commit):

```bash
make archival-freeze-validate
```

Supporting (subset):

```bash
make stewardship-validate
python3 tools/check_freeze_integrity.py
```

**No new validation pipelines** are expected in dormancy.

## Generated artifacts (local, gitignored)

- `var/stewardship_integrity/repository_fingerprint.json`
- `var/immutable_archive/`
- `var/ops_*` (operator hosts)

## Questions

| Question | Answer |
|----------|--------|
| Is the project abandoned? | **No** — dormant, preserved |
| Should we add features? | **No** — restart evaluation first |
| Is silence a problem? | **Often no** — see dormancy policy |
| Who owns preservation? | Operator + engineering (shared, minimal cadence) |

## Preservation cadence (canonical)

| Interval | Action |
|----------|--------|
| **90d** | Archival integrity + reproducibility spot-check (`archival-freeze-validate` or documented subset) |
| **180d** | [offline_ops_recovery_drill.md](../runbooks/offline_ops_recovery_drill.md) |
| **Incident only** | Full `archival-freeze-validate` + emergency preservation audit |

## References

- [final_dormancy_declaration.md](final_dormancy_declaration.md)
- [terminal_preservation_sealing_report.md](terminal_preservation_sealing_report.md)
- [dormancy_operations_policy.md](../governance/dormancy_operations_policy.md)
