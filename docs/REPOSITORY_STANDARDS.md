# Repository standards

Consistency rules for contributors. **Repository consistency is preferred over tooling diversity.**

## Naming conventions

| Kind | Pattern | Example |
|------|---------|---------|
| Runtime JSON | `snake_case.json` under `runtime/` | `health_snapshot.json` |
| Observability module | `runtime_<domain>.py` | `runtime_index.py` |
| CLI command | `kebab-case` | `verify-runtime` |
| ADR | `ADR-NNN-short-topic.md` | `ADR-016-repository-reproducibility-and-maintenance.md` |
| Doc (topic) | `UPPER_SNAKE or Title_Case.md` | `RUNTIME_OPS.md`, `START_HERE.md` |
| Demo script | `NN_description.sh` | `02_runtime_inspection.sh` |
| Make target | `kebab-case` | `runtime-index` |

Do not rename frozen runtime artifacts without ADR + contract test updates.

## Runtime artifact naming

- Exactly **14** filenames — see `observability/runtime_contracts.py`
- Paths: `runtime/<filename>` except sidecars at `OUTPUT_DIR` root (`qualification.json`, `runtime_bundle.zip`)
- Status fields documented in [RUNTIME_LAYOUT_REFERENCE.md](RUNTIME_LAYOUT_REFERENCE.md)

## Docs naming

- Onboarding: `START_HERE.md`, `ARCHITECTURE_MAP.md`, `REPOSITORY_MAP.md`
- Operations: `OPERATOR_*`, `DEPLOYMENT_*`, `RUNTIME_*`, `RELEASE_*`
- Philosophy: `ENGINEERING_PHILOSOPHY.md`, `FAQ.md`, `CONTRIBUTING.md`
- Architecture: `docs/architecture/` for ADRs and frozen contracts

## ADR naming

- Sequential number, kebab-case slug
- Sections: Status, Date, Context, Decision, Consequences, Non-goals
- Link from [architecture/README.md](architecture/README.md)

## Shell script conventions

- `#!/usr/bin/env bash`
- `set -euo pipefail`
- `ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"` for demo scripts
- Dry-run default; `DEMO_RUN=1` to execute
- Echo commands before run; no hidden orchestration

## Deterministic JSON expectations

- Use module `KEY_ORDER` when building artifacts
- Do not add fields outside documented schema without ADR
- Prefer `sort_keys=True` for nested dict serialization in writers

## Makefile philosophy

- Thin wrappers over `python -m newsroom.cli` and `tools/*.py`
- `OUTPUT_DIR` / `RUNTIME_DIR` overridable variables
- Quality targets: `contracts`, `smoke`, `lint`, `quality` — stable section headers
- No recursive Make orchestration graphs

## Tooling

- App deps: `requirements.txt`
- Dev deps: `requirements-dev.txt` (pinned `pytest`, `ruff`)
- CI: `make ci-test` (runtime → smoke → contracts)
- Lint scope: `observability/`, `newsroom/`, `tests/contracts/` — ruff **F** rules only (no whole-repo line-length migration)
- Format: `ruff format` on the same scope via `make format-check`

## Related

- [REPRODUCIBILITY.md](REPRODUCIBILITY.md)
- [CONTRIBUTING.md](CONTRIBUTING.md)
