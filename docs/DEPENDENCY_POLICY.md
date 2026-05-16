# Dependency policy

**Dependency count is treated as operational complexity.**

## Minimal dependencies

- Runtime deps live in `requirements.txt` — application needs only (no pytest in production install).
- Dev deps: `requirements-dev.txt` (pinned `pytest`, `ruff`).
- Prefer **stdlib** in `observability/` and inspection CLIs.

## Stdlib-first preference

New operational tooling should use:

- `json`, `pathlib`, `hashlib`, `subprocess` — not new frameworks.
- Make/bash wrappers — not workflow engines.

## Conservative upgrades

1. Read upstream changelog for breaking API changes.
2. Run `make release-check` locally.
3. Patch version bumps preferred over minor jumps when risk is unclear.
4. Document notable upgrades in [CHANGELOG.md](../CHANGELOG.md).

## Deterministic tooling

- Pinned versions in requirements files.
- Ruff scoped to governance modules (`observability/`, `newsroom/`, `tests/contracts/`).
- CI uses `make ci-test` — no matrix explosion.

## Security updates

- Apply promptly for known CVEs in direct dependencies.
- Report issues per [SECURITY.md](../SECURITY.md).
- Do not commit secrets; `.env` stays local.

## Avoiding ecosystem churn

- No Poetry/monorepo migration without ADR.
- No optional “nice to have” libraries for one-off scripts.
- Question every new dependency: **can stdlib or existing deps do this?**

## Related

- [MAINTENANCE_MODE.md](MAINTENANCE_MODE.md) · [REPRODUCIBILITY.md](REPRODUCIBILITY.md)
