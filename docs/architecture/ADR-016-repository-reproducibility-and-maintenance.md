# ADR-016: Repository reproducibility and maintenance

Status: Accepted  
Date: 2026-05-15

Scope: `docs/REPRODUCIBILITY.md`, `docs/REPOSITORY_STANDARDS.md`, `requirements-dev.txt`, Makefile quality targets, contract test expansion. **No runtime artifact, governance, deployment, or CLI semantic changes.**

## Context

Runtime governance is frozen (ADR-015). Long-term value shifts to **maintainability**: predictable CI, pinned dev tooling, documented reproducibility bounds, and repository standards so new contributors do not reintroduce tooling sprawl.

## Decision

- Document **guaranteed vs not guaranteed** reproducibility in [REPRODUCIBILITY.md](../REPRODUCIBILITY.md).
- Pin dev toolchain in `requirements-dev.txt` (`pytest`, `ruff`).
- Add Makefile targets: `lint`, `format-check`, `contracts`, `smoke`, `quality`; sectioned `ci-test`.
- Add [REPOSITORY_STANDARDS.md](../REPOSITORY_STANDARDS.md) and [REPOSITORY_MAP.md](../REPOSITORY_MAP.md).
- Expand contract tests for stable `runtime-help` / `docs-map` sections and required Makefile targets.
- Lint scope limited to `observability/`, `newsroom/`, `tests/contracts/` — not a whole-repo style migration.
- **Repository consistency is preferred over tooling diversity.**

## Consequences

- **Positive:** CI and local `make quality` align; reproducibility expectations are explicit.
- **Positive:** Contract tests catch accidental Makefile/CLI drift.
- **Negative:** `ruff` does not cover the entire legacy codebase by design.
- **Negative:** Timestamps and model outputs remain intentionally non-deterministic.

## Non-goals

- Poetry, monorepo tooling, heavy build systems, matrix CI.
- New runtime layers, governance semantics, deployment automation.
- MkDocs portals, dashboards, orchestration helpers.
- Mandating identical OpenAI or network outputs.
