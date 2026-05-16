# ADR-027: Preservation readiness and long-horizon survivability (v2.x)

## Status

Accepted (documentation + read-only guardrails)

## Context

The platform is historically traceable and semantically verified. Rare releases and maintainer turnover require explicit survivability without enterprise archival infrastructure.

## Decision

1. Publish `docs/preservation/*` for aging, dependencies, recovery, minimal profile, durability, governance.
2. Add `tools/preservation_guardrails.py` and `tests/preservation/`.
3. No vendoring, rewrite, or runtime contract changes.

## Consequences

- Realistic multi-year posture for low-activity maintenance
- Clear minimal recoverable profile vs feature minimum
- CI-enforced preservation doc presence

## Non-goals

- Offline mirror platform, full reproducible-build program, dependency fork campaign
