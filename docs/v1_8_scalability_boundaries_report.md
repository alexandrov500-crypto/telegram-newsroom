# v1.8 scalability boundaries report

Planning and validation artifact — **no runtime contract changes**.

## Supported Operational Envelope

- **T0–T3** documented in [scalability/operational_topologies.md](scalability/operational_topologies.md)
- Default production path: **T1** single-node production-lite
- Bounded throughput path: **T2** with Redis + `WORKER_RETRY_SAFE` + `PUBLISH_LOCK_STRICT`
- **T4** explicitly unsupported for operations

## Scalability Ceiling Assessment

| Dimension | Ceiling | Binding factor |
|-----------|---------|----------------|
| DB writes | 1 writer | SQLite semantics |
| Workers | ≤ CPU cores (heuristic) | Lock + API limits |
| Queue depth | ~200 sustained = stop | Operator policy |
| Evidence disk | 500 MB warning | Retention discipline |
| Restore | grows with OUTPUT_DIR | Disk I/O |

Deterministic simulations: `tests/scalability/`.

## Multi-Worker Safety Assessment

- Safe only under [scalability/multi_worker_discipline.md](scalability/multi_worker_discipline.md)
- Chaos/soak v1.1/v1.3 validation still authoritative for retry/lock behavior
- Diagnostics flag unsafe Redis-without-strict-lock

## Capacity Planning Guidance

See [scalability/capacity_planning.md](scalability/capacity_planning.md) — thresholds, heuristics, when not to scale.

## PostgreSQL Evolution Assessment

- Documented path only: [scalability/postgresql_evolution_path.md](scalability/postgresql_evolution_path.md)
- **Not implemented** in v1.8
- Many limits are API/publish-bound; Postgres is not a default answer

## Unsupported Deployment Models

Registry: [scalability/unsupported_deployments.md](scalability/unsupported_deployments.md)

## Operational Complexity Risks

| Risk | Mitigation |
|------|------------|
| Accidental K8s/HA | Unsupported registry + governance |
| Worker scale during retry storm | Runbooks + diagnostics |
| Evidence disk fill | Retention + SNAPSHOT runbook |
| Fake dev capacity | Capacity planning honesty |

## Recommended v1.9 Priorities

1. Extended scalability diagnostics integration with nightly JSON artifacts (read-only)
2. Optional queue depth thresholds in operator dashboard (no new frozen artifacts without ADR)
3. Restore duration benchmarks in CI from synthetic bundles
4. PostgreSQL ADR only if measured SQLite pain exceeds ops cost
5. Continue maintenance-first; no default-on flags

## Validation performed

```bash
make scalability-validate
make ci-test
make release-check
make resilience-validate
make governance-validate
```

## Backward compatibility statement

- No new frozen runtime JSON artifacts
- No CLI command additions required for v1.8
- `tools/scalability_diagnostics.py` is read-only opt-in
- Feature flags unchanged (defaults false)
