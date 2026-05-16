# Dormancy risk policy

Risk acceptance for **intentionally dormant** repositories. Complements [governance_restart_risk_matrix.md](governance_restart_risk_matrix.md).

## Acceptable risks (inherent to dormancy)

| Risk | Mitigation | Review |
|------|------------|--------|
| Stale tooling dependencies | Security advisory only; pin if CVE affects checkout/scripts | On advisory |
| Aging documentation links | Fix broken links in preservation PRs only | 180d or on read |
| Reduced operational familiarity | Preservation notice; MAINTAINERS_GUIDE | Onboarding |
| Lower validation frequency | 90d spot-check; full chain on incident | Calendar |
| Slower hotfix response | Accept unless security-critical | Incident |

**These do not justify restart by themselves.**

## Unacceptable risks (always act)

| Risk | Response |
|------|----------|
| Archival corruption | Recovery drill; restore from tags; incident log |
| Governance erosion | Halt merges; preservation audit; restore docs/tags |
| Runtime drift in frozen paths | Reject PR; separate runtime program |
| Undocumented changes to freeze scope | Revert; governance review |
| Tag integrity loss | Restore from remote; never silent retag |
| Moved `v3.2-*` tags | Treat as S1 incident |

## Risk decision rule

```
IF unacceptable risk → act immediately (preservation)
ELIF acceptable risk → monitor on cadence
ELIF "we should modernize" → reject (not a risk; preference)
```

## References

- [ADR-038](../architecture/ADR-038-governance-dormancy-protocol.md)
- [preservation_priority_policy.md](preservation_priority_policy.md)
