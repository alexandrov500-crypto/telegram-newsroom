# Dormancy reactivation trigger guide

**Default:** remain dormant.  
**Companion:** [ADR-037](../architecture/ADR-037-governance-restart-framework.md), [restart_evaluation_template.md](../governance/restart_evaluation_template.md)

## When restart MAY be considered

Only with written evidence and completed evaluation template:

| Trigger | Evidence required |
|---------|-------------------|
| **Critical security exposure** | CVE + exploit path in frozen tree; hotfix insufficient |
| **Platform incompatibility** | Telegram/API breaking change; documented vendor notice |
| **Archival unrecoverability** | Drill failure; kits unverifiable; corruption systemic |
| **Legal/compliance requirement** | Audit letter, regulation citation |
| **Operational impossibility** | Sustained production failure; not preference |

## When restart MUST NOT be triggered

| Driver | Response |
|--------|----------|
| Modernization desire | Defer indefinitely |
| New tooling ideas | Reject |
| Scaling curiosity | See v1.8 scalability docs |
| Ecosystem trends | Non-goal |
| Engineering dissatisfaction | Not operational evidence |
| “Tech debt cleanup” | Hotfix or nothing |
| Team boredom | Not a trigger |
| Manager mandate without evidence | Reject |

## Procedure

1. Confirm trigger class (table above).
2. Complete [restart_evaluation_template.md](../governance/restart_evaluation_template.md).
3. Run [governance_restart_review.md](governance_restart_review.md).
4. If approved for **meta-study only** → docs ADR-039+ draft — still **no code**.
5. Separate decision for any implementation program.

## Cooling-off

After rejection: **30 days** minimum before same theme resubmission ([governance_restart_review.md](governance_restart_review.md)).

## Dormancy preserved during review

While evaluation runs:

- Tags remain unmoved
- Dormancy cadence may pause for audits but **does not imply approval**
- No `feature/*` branches for implementation

## References

- [governance_suspension_matrix.md](../governance/governance_suspension_matrix.md)
- [restart_readiness_declaration.md](../releases/restart_readiness_declaration.md)
