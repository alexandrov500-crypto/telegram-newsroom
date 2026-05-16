# Scaling governance

Controls accidental platform creep while allowing bounded evolution.

## Scaling review criteria

Require written review (issue or ADR) when change:

- Adds mandatory infrastructure (Postgres, K8s, bus)
- Changes frozen runtime artifact schema
- Introduces new default-on behavior
- Expands worker count guidance beyond T2 envelope
- Claims HA or multi-region support

## Operational burden thresholds

| Burden | Accept | Reject |
|--------|--------|--------|
| New always-on daemon | No | Unless opt-in tool |
| New env var default `true` | No | Breaks v1.0 contract |
| 24/7 on-call for new component | No | Production-lite limit |
| Manual runbook step | Yes | Preferred mitigation |

## Complexity budgeting

- Prefer documentation + diagnostics over new services
- One concern per ADR (e.g. Postgres ≠ microservices)
- Reuse `tools/*_diagnostics.py` pattern (read-only)

## Evolution gates

1. **Document** — topology + capacity + unsupported list
2. **Simulate** — `tests/scalability/` bounded tests
3. **Diagnose** — `scalability_diagnostics.py`
4. **Runbook** — operator path before code default change
5. **ADR** — architecture escalation only after 1–4

## Do not scale this way policy

- Add workers before queue/retry health green
- Migrate database under pressure
- Introduce orchestration to avoid runbooks
- Ship “experimental” flags default-on in production

## Architecture escalation triggers

Escalate to architecture / ADR when:

- Sustained queue > 200 with healthy upstream
- WAL > 500 MB recurring after maintenance
- Restore drills exceed maintenance window regularly
- Multi-node requirement stated by stakeholders
- Security boundary change (new trust zone)

Escalation **does not** auto-approve Postgres or microservices — it starts evidence collection.

## Relation to release governance

- [compatibility_policy.md](../compatibility_policy.md) — contract freeze
- [release_governance.md](../release_governance.md) — release classes
- [feature_flag_governance.md](../feature_flag_governance.md) — opt-in behavior
