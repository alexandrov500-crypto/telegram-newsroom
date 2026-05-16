# ADR-031: Operational analytics layer (v3.2 P2)

**Status:** Accepted  
**Date:** 2026-05-16  
**Depends on:** ADR-030 (P1 read-only tooling)

## Decision

Add an **offline analytics consolidation layer** on top of `var/ops_history` snapshots:

- `tools/ops_analytics_aggregate.py`
- `tools/ops_visualize.py` (static SVG)
- `tools/ops_archive.py`
- `tools/generate_shift_handoff.py`

No changes to publish, retry, scheduler, lock, or live runtime paths.

## Allowed

| Capability | Mechanism |
|------------|-----------|
| Offline analytics | Read JSON snapshots only |
| Snapshot aggregation | `utils/ops_analytics.py` |
| Static reports | JSON + Markdown under `var/ops_reports/` |
| Trend computation | Counter deltas, rolling means, percentiles |
| Bounded retention | P1 rotation + P2 gzip archive |
| Read-only enrichment | Derived fields in analytics output only |

## Forbidden

- Real-time orchestration or streaming
- Metrics-driven automation / auto-retry
- Runtime feedback loops into publisher or worker
- Distributed telemetry or external vendors (Datadog, etc.)
- Background daemons or network listener services
- Auto-remediation

## Storage bounds

| Location | Limit |
|----------|-------|
| `var/ops_history/` | 200 files / 20MB (P1 rotate) |
| `var/ops_archive/` | 50MB per archive run (configurable in code) |
| `var/ops_reports/` | Operator-managed; regenerate anytime |
| Analytics RAM | Default ≤200 snapshots per run |

## Safety guarantees

- **Read-only:** no Telegram API, no Redis writes
- **Deterministic:** same inputs → same JSON/SVG (UTC timestamps in meta only)
- **Corrupt tolerance:** skip invalid snapshots; report in `skipped_corrupt`
- **Rollback:** delete `var/ops_reports/` and `var/ops_archive/`; stop running tools

## Deterministic analytics requirements

- Fixed percentile algorithm (linear interpolation)
- Sorted file iteration by filename
- No random sampling; no wall-clock except `generated_at` header
- CI tests use fixture snapshots with fixed timestamps

## CI

- `make ops-analytics-validate`
- No network; no live Redis/Telegram

## References

- [metrics_retention_policy.md](../operations/metrics_retention_policy.md)
- [v3_2_p2_exit_criteria.md](../releases/v3_2_p2_exit_criteria.md)
