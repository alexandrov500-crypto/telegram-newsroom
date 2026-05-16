# ADR-001: Bounded runtime state

Status: Accepted  
Date: 2026-05-15

Scope: JSON and small files under `RUNTIME_STATE_DIR`, related compaction and caps.

## Context

The service needs **durable, inspectable** operational state (timeline, events, suppression, drift snapshots) without turning the host into an append-only log warehouse. Operators must be able to copy a directory or zip and reason about incidents offline.

## Decision

Treat runtime state as **explicitly bounded**:

- Prefer **fixed-size or capped** structures where the code already enforces limits (snapshot counts, storage budgets, flush intervals — see `app/config.py` settings and runtime store helpers).
- Use **compaction** and pruning for long-lived JSON (e.g. event history / timeline strategies documented alongside implementation).
- Pair **retention** at the DB layer (`RETENTION_*`) with **artifact retention** for CI/output roots (`docs/RUNTIME_RETENTION.md`).
- Expose **integrity** checks (`runtime-integrity-check`, bundle `integrity.json`) so corruption is detected early.

## Consequences

- **Positive:** Predictable disk use; postmortems stay reproducible; bundles remain small enough for email/CI artifacts.
- **Negative:** Very old forensic detail may be dropped; teams must rely on external backups for long archival if required.

## Non-goals

- No requirement for an internal time-series database.
- No unbounded “debug always on” JSON streams in production paths.
