# ADR-024: v2 transition strategy (stewardship; planning only)

## Status

Accepted (documentation + read-only guardrails)

## Context

The platform is mature across hardening, governance, security, scalability bounds, and operational intelligence. Long-term evolution must avoid architectural entropy and speculative rewrites.

## Decision

1. Publish architectural preservation, v2 transition strategy, technical debt governance, complexity budget, evolution matrix, scalability realities, maintainer longevity, and operational philosophy.
2. Add read-only `tools/architecture_guardrails.py` for stewardship checks.
3. **Do not** implement v2, breaking contracts, or mandatory new infrastructure.

## Consequences

- Clear gates for any future major version
- Reduced platform-creep risk via documented anti-patterns
- Maintainers have 3–5 year posture without bureaucracy explosion

## Non-goals

- v2 rewrite, K8s-native redesign, microservices, mandatory Postgres, event platform, autonomous control plane
