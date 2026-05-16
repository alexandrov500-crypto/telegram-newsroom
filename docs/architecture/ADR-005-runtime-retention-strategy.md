# ADR-005: Runtime retention strategy

Status: Accepted  
Date: 2026-05-15

Scope: `utils/runtime_retention.py`, `tools/runtime_retention.py`, DB retention settings.

## Context

CI roots and operator laptops accumulate `runtime_bundle.zip`, regression JSON, and HTML reports. Without a policy, directories grow indefinitely; with an over-engineered policy, operators lose trust (silent deletes, cloud-only archives).

## Decision

Implement **deterministic, filesystem-local retention**:

- Scan **configured roots** only (artifacts, optional baselines, optional reports); match basenames by explicit rules (see `docs/RUNTIME_RETENTION.md`).
- Prefer **count + age** style policies with stable sorting so deletes are reproducible.
- Keep **DB retention** (`RETENTION_PROCESSED_RAW_DAYS`, etc.) separate but conceptually aligned: both aim at bounded storage, different layers.

`runtime_ops` exposes retention as a **single sequential step** with skip flags for CI (`--skip-retention`).

## Consequences

- **Positive:** Predictable cleanup; easy to explain in runbooks; no external archival SaaS required.
- **Negative:** Long-term cold storage is the operator’s responsibility (e.g. object storage outside this repo).

## Non-goals

- No distributed garbage collector.
- No content-addressable global artifact registry in-repo.
