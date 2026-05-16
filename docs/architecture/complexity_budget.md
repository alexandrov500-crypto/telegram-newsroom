# Complexity budget framework

Formal mechanism against uncontrolled growth. Scores are **heuristic** for ADR discussions — not automated enforcement of v2.

## Scoring dimensions (0–5 each, higher = more burden)

| Dimension | 0 | 3 | 5 |
|-----------|---|---|---|
| **Operational burden** | Read-only doc | New opt-in CLI | New required daemon |
| **Maintenance cost** | No code | Small module | Cross-cutting refactor |
| **Release overhead** | Doc-only | New make target | New mandatory CI service |
| **Observability cost** | Reuses JSON artifacts | New read-only tool | Mandatory external backend |
| **Migration cost** | None | Opt-in flag | Breaking schema |
| **Governance impact** | None | New runbook | Contract freeze change |

**Proposal total** = sum of six dimensions (max 30).

## Budget thresholds

| Total | Decision |
|-------|----------|
| 0–8 | Proceed (docs/small tools) |
| 9–14 | Proceed with ADR note |
| 15–20 | ADR required + runbook |
| 21–26 | Deferred unless measured pain |
| 27–30 | Reject or v2 program only |

## Current baseline (v1.x stewardship era)

Approximate standing budget consumption (not to exceed without review):

| Area | Score | Notes |
|------|-------|-------|
| Frozen runtime contracts | 3 | Maintenance, not optional |
| Opt-in flags (5) | 6 | Bounded registry |
| Chaos/soak/intelligence tests | 8 | CI-safe, opt-in runtime |
| Read-only tools (`tools/*`) | 6 | No mandatory telemetry |
| Scaling docs + runbooks | 4 | Advisory |

**Headroom policy:** prefer proposals ≤8 total; batch related changes in one ADR.

## Anti-growth rules

1. New tool must justify why existing tool cannot extend.
2. New doc type must link to ADR or runbook.
3. New env var defaults to off.
4. No duplicate governance (one compatibility policy SSOT).
5. Retire experiments that fail validation for two release cycles.

## Complexity budget review

Include in proposal template:

```text
Complexity scores: ops _ / maint _ / release _ / obs _ / migr _ / gov _
Total: _ / 30
Measured pain: yes/no (evidence link)
Alternatives rejected: ...
```

Use [architecture_guardrails.py](../../tools/architecture_guardrails.py) for read-only hints.
