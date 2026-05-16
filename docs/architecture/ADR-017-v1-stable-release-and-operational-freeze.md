# ADR-017: v1.0.0 stable release and operational freeze

Status: Accepted  
Date: 2026-05-15

Scope: `newsroom/_version.py`, packaging metadata, `make release-check`, OSS policy docs. **No runtime artifact, governance, deployment, or CLI semantic changes.**

## Context

ADR-015/016 froze contracts and improved repository reproducibility. The project is ready for a **public stable identity** (v1.0.0) with clear maintenance boundaries and release gates — without implying platform-scale features.

## Decision

- Set **VERSION = 1.0.0**, **RELEASE_STATUS = stable** in `newsroom/_version.py` (SSOT).
- Declare **operational freeze** on runtime governance in README, START_HERE, RUNTIME_MATURITY, STABILITY_GUARANTEES.
- Add `make release-check` (contracts → smoke → quality → packaging tests).
- Rename bundle qualification target to `make release-qualify` (avoids collision).
- Add LICENSE (MIT), MANIFEST.in, SECURITY.md, SUPPORT.md, RELEASE_FINALIZATION.md.
- Contract tests for version and packaging consistency.

## Consequences

- **Positive:** Clear OSS expectations; deterministic pre-tag gate.
- **Positive:** Single version source reduces drift with `pyproject.toml` and `app.versioning`.
- **Negative:** `requires-python <3.13` pins 3.12 until explicitly widened.
- **Negative:** Bundle qualification command renamed — update operator scripts referencing old `release-check`.

## Non-goals

- Automated release bots, semantic-release, deployment CI.
- New runtime/governance layers or lifecycle changes.
- Telemetry, orchestration, dashboards, cloud abstractions.
