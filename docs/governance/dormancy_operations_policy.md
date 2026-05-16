# Dormancy operations policy

Reduced operational cadence for a **dormant** v3.2 archival repository. Supersedes active [stewardship_operations_calendar.md](stewardship_operations_calendar.md) for **frequency** only — hotfix rules still apply when work occurs.

## “No activity is healthy” doctrine

- **Zero commits for quarters** may indicate correct dormancy.
- Lack of roadmap meetings is **expected**, not neglect.
- Do not schedule “backlog grooming” for this repository.
- Activity spikes warrant **classification**: preservation vs unauthorized evolution.

## Reduced cadence

### Every 90 days (preservation)

| Task | Action | Owner |
|------|--------|-------|
| Archival integrity | `build_archival_integrity_seal.py` or `make archival-freeze-validate` on canonical checkout | Engineering |
| Reproducibility spot-check | `OPS_FROZEN_UTC=2026-05-16T12:00:00Z make immutable-baseline-validate` (or document equivalent) | Engineering |
| Freeze integrity | `check_freeze_integrity.py` | Engineering |

**Record:** date + pass/fail in internal log (not required in git).

### Every 180 days (recovery)

| Task | Action | Owner |
|------|--------|-------|
| Offline recovery drill | [offline_ops_recovery_drill.md](../runbooks/offline_ops_recovery_drill.md) | Operator + engineering |
| Archive readability | Verify `var/ops_archive/` gzip samples open; spot-read manifest | Operator |

### Only on incident

| Trigger | Action |
|---------|--------|
| Suspected freeze breach | Full `archival-freeze-validate` + preservation audit |
| Security advisory affecting repo | Hotfix review per maintenance procedure; no scope creep |
| Governance restart proposal | [governance_restart_review.md](../runbooks/governance_restart_review.md) |
| Corruption / lost kits | Emergency preservation audit + recovery drill |

## Acceptable inactivity expectations

| Period | Expected state |
|--------|----------------|
| 0–90d | No commits normal |
| 90d | Preservation check (may be only activity) |
| 180d | Recovery drill if ops still use snapshots |
| >1y | Tags unchanged; ADR chain intact |

## What is not required in dormancy

- Daily diagnostics snapshots (host-dependent; not repo obligation)
- Weekly release kits
- Monthly analytics refreshes in git
- New documentation beyond preservation fixes

## Escalation

Preservation failure → [dormancy_risk_policy.md](dormancy_risk_policy.md) unacceptable risks.  
Expansion desire → [dormancy_reactivation_trigger_guide.md](../runbooks/dormancy_reactivation_trigger_guide.md) — default decline.

## References

- [ADR-038](../architecture/ADR-038-governance-dormancy-protocol.md)
- [repository_preservation_notice.md](../releases/repository_preservation_notice.md)
