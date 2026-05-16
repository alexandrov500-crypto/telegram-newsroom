# Operational philosophy (codified)

Stewardship principles for long-term evolution. Complements [ENGINEERING_PHILOSOPHY.md](../ENGINEERING_PHILOSOPHY.md).

## Operational-first mindset

- Ship operability before features.
- Every production path needs inspect and recover story.
- If operators cannot explain it from docs + JSON, it is not done.

## Deterministic recovery preference

- Prefer reproducible artifacts over live debugging alone.
- `verify-runtime`, `validate-recovery`, baselines — first-class.
- Surprises belong in runbooks, not tribal knowledge.

## Maintenance-first scaling

- Scale discipline before scale hardware ([capacity_planning.md](../scalability/capacity_planning.md)).
- Forecasts advise; operators decide ([operational_intelligence.md](../operational_intelligence.md)).
- Stop scaling when retry/WAL/evidence red ([scaling runbooks](../runbooks/scaling/)).

## Bounded automation

| Allowed | Not allowed |
|---------|-------------|
| Read-only diagnostics | Auto-delete production data |
| Opt-in flags default off | Self-healing without confirmation |
| CI validation | Autonomous deploy bots in-repo |
| Advisory forecasts | ML orchestration |

## Explicit unsupported states

- T4 topologies, hybrid DB, fake HA — documented, not hidden.
- Tools may warn; they must not pretend support.

## Observability without dependency explosion

- JSON artifacts + CLI + optional static dashboard.
- No mandatory Prometheus/Grafana/Jaeger.
- Intelligence tools consume existing signals.

## Operator agency preservation

- Operators can ignore recommendations.
- No silent mutation of queues, DB, or evidence.
- Escalation paths are human ([scaling_governance.md](../scalability/scaling_governance.md)).

## Relationship to v2

v2 must not overturn this philosophy without explicit operator contract change and ADR superseding this document.
