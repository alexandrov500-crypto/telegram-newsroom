# ADR-011: Runtime baseline and drift semantics

Status: Accepted  
Date: 2026-05-15

Scope: `observability/runtime_baseline.py`, `runtime/runtime_baseline.json`, `runtime/drift_report.json`, `newsroom.cli create-baseline`, `newsroom.cli compare-baseline`.

## Context

Bounded audit history shows recent qualification trends, but operators also need a **fixed reference snapshot** and **deterministic drift checks** against it — without statistical engines, ML, or telemetry warehouses.

## Decision

- Store **`runtime_baseline.json`** as a known-good operational metadata snapshot (statuses, durations, schema versions, audit `status_summary`).
- Emit **`drift_report.json`** from fixed-threshold comparison (`RUNTIME_DURATION_WARNING_THRESHOLD_SEC = 15.0`).
- Drift statuses: **OK**, **WARNING**, **FAIL** with explicit rules (schema incompatibility, missing artifacts → FAIL; qualification downgrade, incident increase, duration delta, version drift → WARNING).
- CLI: **`create-baseline`**, **`compare-baseline [--json] [--strict]`**; nightly ops writes drift report after history update when baseline workflow runs.
- **Inspection-only** — no artifact mutation, no adaptive thresholds, no anomaly platform.

**Baseline comparison is deterministic operational inspection, not anomaly analytics.**

## Consequences

- **Positive:** Shell/CI can gate on drift; comparisons are reproducible and explainable via `drift_warnings`.
- **Negative:** Baseline must be refreshed manually when intentional operational change occurs (`create-baseline`).
- **Negative:** Duration threshold is fixed — not environment-adaptive.

## Non-goals

- Anomaly detection, ML/statistical baselines, adaptive thresholds, telemetry analytics, time-series analysis, forecasting.
- Distributed baseline storage, background comparison daemons, automatic remediation, performance profiling platforms.
