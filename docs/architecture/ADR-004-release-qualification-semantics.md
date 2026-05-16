# ADR-004: Release qualification semantics

Status: Accepted  
Date: 2026-05-15

Scope: `utils/release_qualification.py`, `tools/release_qualification.py`, integration from `utils/runtime_ops.py`.

## Context

Before promoting a build or image, operators need a **read-only** decision from frozen artifacts (zip bundles), not from live cluster probes. The gate must be **explainable** (JSON + human report) and **strict enough for CI** without pretending to be a full security audit.

## Decision

- **Inputs:** Current and baseline `runtime_bundle.zip` paths only (plus flags).
- **Outputs:** `qualification_status` ∈ {`OK`, `WARNING`, `FAIL`}, `release_ready` boolean, structured `checks`, sorted warnings/failures.
- **Regression:** Reuse `run_regression_comparison`; overall `FAIL` blocks release when `require_regression_ok` is set.
- **WARNING vs FAIL:** `FAIL` marks hard problems (integrity, missing critical payloads when required, failed regression thresholds). `WARNING` marks softer drift; `release_ready` may still be true when `allow_warning` is enabled.
- **Strict CLI mode:** Non-zero exit unless status is `OK` (and bundle warnings clean per flag), suitable for CI gates.

## Consequences

- **Positive:** Same qualification logic locally and in CI; artifacts are reviewable in postmortems.
- **Negative:** Self-baseline CI scenarios may need explicit env skips for inherently volatile fields—documented in `docs/CI_CD.md`, not hidden magic in core logic.

## Non-goals

- No automatic canary rollout or traffic shifting.
- No cryptographic signing of bundles in this ADR (could be a future separate ADR if needed).
