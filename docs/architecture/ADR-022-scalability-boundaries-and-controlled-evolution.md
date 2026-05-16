# ADR-022: Scalability boundaries and controlled evolution (v1.8)

## Status

Accepted (planning + validation only)

## Context

After v1.6 security hardening, operators need explicit scalability ceilings and evolution gates without mandating Postgres, Kubernetes, or microservices.

## Decision

1. Classify operational topologies T0–T4 with T4 explicitly unsupported.
2. Add read-only `tools/scalability_diagnostics.py` and `tests/scalability/` bounded simulations.
3. Document capacity planning, multi-worker discipline, PostgreSQL **evolution path only** (no implementation).
4. Add scaling runbooks and governance policy.
5. **No** frozen runtime contract changes; **no** default-on feature flags.

## Consequences

- Operators gain honest boundaries and escalation paths.
- Future Postgres or distributed work requires separate ADR + migration program.
- CI gains `make scalability-validate`.

## Non-goals

- Distributed rewrite, K8s-first design, mandatory PostgreSQL, event platform, microservice split.
