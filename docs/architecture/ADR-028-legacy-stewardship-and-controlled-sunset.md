# ADR-028: Legacy stewardship and controlled sunset (v2.x)

## Status

Accepted (documentation + read-only guardrails)

## Context

Preservation readiness (ADR-027) addresses dependency aging. Maintainers also need legacy-state definition and sunset paths without abandonment or rewrite pressure.

## Decision

1. Publish `docs/legacy/*` for legacy state, sunset scenarios, recoverability, envelope, governance, anti-patterns.
2. Add `tools/legacy_guardrails.py` and `tests/legacy/`.
3. No shutdown automation, archive-only conversion, or runtime contract changes.

## Consequences

- Clear legacy vs dormant vs active stewardship
- Reduced governance inflation risk during low activity
- CI-enforced legacy doc presence

## Non-goals

- Forced deprecation programs, enterprise lifecycle bureaucracy, abandonment automation
