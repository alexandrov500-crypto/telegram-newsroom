# ADR-003: No orchestration / workflow platform

Status: Accepted  
Date: 2026-05-15

Scope: `tools/runtime_ops.py`, CI workflows, Makefile targets.

## Context

Sequential operational steps (preflight → benchmark → … → retention) could be modeled in Temporal/Airflow/Kubernetes Jobs, but that introduces **infrastructure ownership**, **state stores**, and **retry semantics** unrelated to the core newsroom problem on a small VPS.

## Decision

Use **composition, not orchestration**:

- A plain **for-loop** order in `run_nightly_check` and explicit subprocess-free calls into existing modules.
- CI workflows are **linear shell steps** with pinned Python and explicit artifacts—no DAG engine.
- Operators chain `make` targets or scripts; there is **no** persisted workflow run ID inside the app.

## Consequences

- **Positive:** Minimal moving parts; easy code review; reproducible local runs.
- **Negative:** No built-in cross-machine fan-out, cron replacement, or automatic retry policies beyond what GitHub Actions provides.

## Non-goals

- No in-repo workflow DSL or YAML-defined state machines for production runtime.
- No requirement for Redis solely to coordinate ops steps.
