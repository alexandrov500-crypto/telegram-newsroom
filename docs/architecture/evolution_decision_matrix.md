# Evolution decision matrix

Score proposals **Low / Medium / High** per column. Use for ADRs and issue triage.

## Criteria

| Criterion | Low | Medium | High |
|-----------|-----|--------|------|
| **Operational value** | Nice-to-have | Reduces incident time | Prevents data loss / outage class |
| **Recovery impact** | No recovery path change | New runbook step | Changes restore/verify semantics |
| **Governance impact** | Doc only | New make target | Frozen contract change |
| **Complexity growth** | ≤8 budget | 9–14 budget | ≥15 budget |
| **Backward compatibility** | Fully compatible | Opt-in break | Breaking default |
| **Operator burden** | Less work | Neutral | More daily tasks |
| **Maintenance sustainability** | One module | Cross-module | New subsystem |

## Decision rules

| Pattern | Outcome |
|---------|---------|
| Any **High** in governance or compatibility | ADR + maintainer review |
| High complexity + Low operational value | Reject |
| High operational value + Medium everything | Proceed with ADR |
| Two+ High in operator burden + complexity | Defer or simplify |
| Breaking compatibility | v2 gate only ([v2_transition_strategy.md](v2_transition_strategy.md)) |

## Example evaluations

### Add read-only forecast tool (v1.9 pattern)

- Operational value: Medium
- Recovery: Low
- Governance: Low
- Complexity: ~9
- Compatibility: Low
- Operator burden: Low (reduces)
- **Outcome:** Accept

### Mandatory PostgreSQL

- Operational value: Medium (context-dependent)
- Recovery: High
- Governance: High
- Complexity: 25+
- Compatibility: High
- Operator burden: High
- **Outcome:** v2 program only; not incremental

### New frozen runtime artifact

- Governance: High
- Compatibility: High
- **Outcome:** v2 or explicit major ADR with migration

## Workflow

1. Proposer fills matrix in issue/ADR.
2. Run `python3 tools/architecture_guardrails.py`.
3. Link to [technical_debt_governance.md](technical_debt_governance.md) class.
4. Merge only if outcome matches [architectural_preservation.md](architectural_preservation.md).
