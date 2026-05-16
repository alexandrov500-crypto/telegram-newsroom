# ADR-026: Historical traceability and ecosystem continuity (v2.x)

## Status

Accepted (documentation + read-only guardrails)

## Context

After semantics formalization (ADR-025), maintainers need recoverable institutional memory across years without compliance bureaucracy.

## Decision

1. Publish `docs/stewardship/*` lineage, archaeology, and continuity docs.
2. Add `tools/history_guardrails.py` and `tests/traceability/`.
3. No git rewrite, no release infrastructure change, no runtime contract change.

## Consequences

- Safer succession and audit-friendly decision trail
- CI-enforced stewardship doc presence
- Bounded doc set — link SSOTs instead of duplicating

## Non-goals

- Enterprise compliance archive, telemetry history platform, contributor management bureaucracy
