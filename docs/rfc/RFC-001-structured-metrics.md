# RFC-001: Structured metrics and Prometheus alignment

**Status:** Draft · **Target:** v1.1 opt-in

## Problem

`utils/metrics.py` counters feed `/metrics` via `utils/prometheus_export.py`, but some signals are stale (`publish_retries` never incremented in production) and `utils/redis_transport_metrics.py` is omitted from export.

## Proposal

- Introduce `METRICS_EXPORT=legacy|extended` (default `legacy`).
- **Extended:** merge redis transport snapshot; label synthetic soak-only counters; optional histograms for job latency (bounded cardinality).
- Document counter catalog in `docs/METRICS_REFERENCE.md` (new, when implemented).

## Non-goals

- Mandatory Prometheus/Grafana stack
- New runtime JSON artifacts

## Acceptance

- Default export byte-identical to v1.0.0 when `METRICS_EXPORT=legacy`
- Contract test for counter list stability in legacy mode
