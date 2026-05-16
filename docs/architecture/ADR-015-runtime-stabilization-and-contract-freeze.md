# ADR-015: Runtime stabilization and contract freeze

Status: Accepted  
Date: 2026-05-15

Scope: documentation, `observability/runtime_contracts.py`, `tests/contracts/`, CLI flag consistency, Makefile `runtime-help`. **No new runtime artifacts or governance modules.**

## Context

ADR-001–014 delivered a complete offline inspection stack (health through unified index). Continuing to add governance layers would increase cognitive load without proportional operator value. The project should shift from **adding architecture** to **stabilizing architecture** for production-lite releases.

## Decision

- Declare the **runtime governance model operationally complete**.
- Freeze contracts in [RUNTIME_CONTRACTS.md](RUNTIME_CONTRACTS.md) and `observability/runtime_contracts.py`.
- Add operator docs: [OPERATOR_QUICKSTART.md](../OPERATOR_QUICKSTART.md), [RUNTIME_LAYOUT_REFERENCE.md](../RUNTIME_LAYOUT_REFERENCE.md), [RELEASE_CHECKLIST.md](../RELEASE_CHECKLIST.md).
- Add **contract tests** (`tests/contracts/`) separate from smoke tests.
- Unify inspection CLI flags (`--path`, `--json`, `--strict`, `--write`) via `newsroom.cli.inspection_common`.
- Add `make runtime-help` for discoverability.
- **No new runtime JSON artifacts** and **no new validation subsystems**.

## Consequences

- **Positive:** Release discipline, predictable interfaces, lower onboarding cost.
- **Positive:** Contract tests catch accidental renames or lifecycle drift in CI.
- **Negative:** Evolution requires explicit contract version bumps and ADR updates.
- **Negative:** Experimental features (baseline, hints) remain documented but not stability-guaranteed.

## Non-goals

- New governance reports, policy domains, orchestration semantics, telemetry concepts.
- Expanding lifecycle graph, artifact taxonomy, or runtime categories.
- Platform-scale governance, admission control, or enforcement infrastructure.
