# Governance restart risk matrix

Risk scoring for restart proposals. Use with [restart_evaluation_template.md](restart_evaluation_template.md).

**Scale:** Severity (S1 highest) · Likelihood (L1 highest)

## Risks

### Runtime destabilization

| | |
|--|--|
| **Description** | Publish/retry/scheduler/lock/contract changes bundled with ops work |
| **Severity** | S1 |
| **Likelihood** | L2 (common if restart undisciplined) |
| **Containment** | Separate runtime ADR program; no ops PR touches `publisher/` |
| **Rejection threshold** | Any unscoped runtime diff → **reject** |

### Governance erosion

| | |
|--|--|
| **Description** | Skipped reviews, moved tags, deleted certification docs |
| **Severity** | S1 |
| **Likelihood** | L3 |
| **Containment** | Preservation audit; immutable tags policy |
| **Rejection threshold** | Proposal moves `v3.2-operational-tooling-freeze` → **reject** |

### Platform creep

| | |
|--|--|
| **Description** | Dashboards, telemetry pipelines, ops SaaS |
| **Severity** | S1 |
| **Likelihood** | L2 |
| **Containment** | ADR-034/036 forbidden list; risk review |
| **Rejection threshold** | Live/network ops dependency → **reject** |

### Operational complexity

| | |
|--|--|
| **Description** | More tools, targets, and artifacts than operators can run |
| **Severity** | S2 |
| **Likelihood** | L2 |
| **Containment** | Cap Makefile targets; MAINTAINERS_GUIDE only |
| **Rejection threshold** | >3 new operator-facing tools without study → **defer** |

### Reproducibility degradation

| | |
|--|--|
| **Description** | Non-deterministic exports, wall-clock-only CI |
| **Severity** | S2 |
| **Likelihood** | L3 |
| **Containment** | `OPS_FROZEN_UTC`; fixture tests mandatory |
| **Rejection threshold** | Cannot define deterministic test plan → **reject** |

### Observability overgrowth

| | |
|--|--|
| **Description** | Metrics driving behavior; real-time orchestration |
| **Severity** | S1 |
| **Likelihood** | L2 |
| **Containment** | Offline snapshot model only |
| **Rejection threshold** | Feedback loop into publisher → **reject** |

### Maintenance burden

| | |
|--|--|
| **Description** | Permanent increase in steward cadence/complexity |
| **Severity** | S2 |
| **Likelihood** | L2 |
| **Containment** | [stewardship_operations_calendar.md](stewardship_operations_calendar.md) |
| **Rejection threshold** | No owner for 90d audit → **defer** |

## Aggregate scoring

| Combined score | Action |
|----------------|--------|
| Any S1 + L1/L2 unmitigated | **Reject** |
| Two S2 + L2 | **Defer** |
| All mitigated + evidence | **Proceed to meta-study** (docs only) |

## References

- [governance_restart_review.md](../runbooks/governance_restart_review.md)
