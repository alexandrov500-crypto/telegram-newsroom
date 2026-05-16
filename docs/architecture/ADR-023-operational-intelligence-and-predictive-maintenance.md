# ADR-023: Operational intelligence and predictive maintenance (v1.9)

## Status

Accepted (advisory tooling only)

## Context

Operators need earlier degradation visibility and maintenance guidance without building an observability platform or autonomous control plane.

## Decision

1. Add deterministic trend, health, and recovery intelligence utilities.
2. Add read-only CLI tools (`maintenance_forecast`, `drift_forecast`, `maintenance_recommendations`, `ops_summary`).
3. Document philosophy and limits in `docs/operational_intelligence.md`.
4. No runtime contract changes; no automatic remediation.

## Consequences

- Lower cognitive load via consolidated advisory CLI.
- Forecasts remain explainable and bounded.
- History samples are operator-managed optional inputs.

## Non-goals

- ML infrastructure, autonomous remediation, mandatory telemetry backend, web UI dashboard.
