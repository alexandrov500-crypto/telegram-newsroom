# ADR-006: Runtime reporting semantics

Status: Accepted  
Date: 2026-05-15

Scope: `observability/runtime_report.py`, `runtime/runtime_report.json`, `newsroom.cli health --report`.

## Context

Health snapshots answer “what are the headline counters and pipeline status?” Operators also need a **single portable inspection document** that ties together artifact presence, domain-level step status, bundle metadata, and a coarse **incident level** for shell/CI — without adopting a metrics or alerting platform.

## Decision

- Emit **`{output_dir}/runtime/runtime_report.json`** after nightly ops, immediately following the health snapshot (latest-only, atomic replace).
- Build reports **deterministically** from the ops report + health snapshot + on-disk inventory (stdlib only).
- Classify **`incident_level`** ∈ {`NONE`, `WARNING`, `ERROR`} with explicit rules; populate `incident_summary` and `warnings` lists — **no notifications**, no external integrations.
- Expose **`python -m newsroom.cli health --report [--strict]`** for offline review and automation exit codes.
- Treat reports as **operational inspection artifacts**, not time-series telemetry.

## Consequences

- **Positive:** Postmortems and CI can grep one JSON file; bundle zip metadata is captured when present; missing artifacts degrade to WARNING, not crash.
- **Negative:** `step_status` domains are a **heuristic mapping** from nightly ops steps, not live pipeline internals; historical reports are not retained in-repo.

## Non-goals

- No Prometheus, Grafana, OpenTelemetry, Sentry, ELK, Loki, or metrics servers.
- No alerting, paging, or webhook fan-out.
- No background collectors, websocket streaming, or event buses.
- No historical report retention policy in application code.
