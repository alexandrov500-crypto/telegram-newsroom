# Final dormancy declaration

**Effective:** 2026-05-16  
**State:** DORMANT  
**ADR:** [ADR-038](../architecture/ADR-038-governance-dormancy-protocol.md)

## Declarations

1. This repository is **now dormant**.
2. There is **no active engineering lifecycle** for v3.2 tooling or archival scope.
3. There is **no active stewardship expansion** — preservation only.
4. **Preservation is the primary responsibility** of maintainers.
5. **Archival continuity** is prioritized over evolution.
6. **Reactivation is exceptional** and governance-gated ([ADR-037](../architecture/ADR-037-governance-restart-framework.md)).

## What maintainers do

- Follow [dormancy_operations_policy.md](../governance/dormancy_operations_policy.md) (90d/180d)
- Treat inactivity as healthy unless unacceptable risk ([dormancy_risk_policy.md](../governance/dormancy_risk_policy.md))

## What maintainers do not do

- Plan roadmaps
- Expect quarterly feature delivery from this repo
- Add tooling without restart approval

## Verification (on cadence, not continuously)

```bash
git checkout v3.2-archival-baseline
make archival-freeze-validate
```

## Sign-off

| Role | Acknowledged | Date |
|------|--------------|------|
| Engineering | ☑ | 2026-05-16 |
| Governance | ☐ | |
| Operator | ☐ | |
