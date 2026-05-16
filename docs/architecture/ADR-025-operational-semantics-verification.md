# ADR-025: Operational semantics and invariant verification (v2.x)

## Status

Accepted (documentation + verification only)

## Context

The platform is strategically preserved (ADR-024) but operators need explicit invariants, forbidden states, and recovery semantics to reduce ambiguity under failure.

## Decision

1. Publish semantics registry docs and consistency matrix.
2. Add `tests/semantics/` deterministic verification.
3. Add read-only `tools/semantics_guardrails.py`.
4. **No** runtime rewrite, formal methods platform, or contract changes.

## Consequences

- Clearer operator expectations and recovery honesty
- CI-enforced doc/tool presence
- Semantics evolve via semantics_governance.md

## Non-goals

- Theorem provers, model checking, distributed consensus verification, static typing campaign
