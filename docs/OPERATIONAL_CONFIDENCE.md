# Operational confidence (v1.0.0)

Engineering validation summary — not marketing. Confirms the project is maintainable in real use without new subsystems.

## Installation confidence

| Check | Status |
|-------|--------|
| `make install-dev` documented | Yes — [QUICKSTART.md](QUICKSTART.md), [DEPLOYMENT_QUICKSTART.md](DEPLOYMENT_QUICKSTART.md) |
| Dev tools pinned | `requirements-dev.txt` |
| Python version | 3.12 recommended; see [REAL_WORLD_VALIDATION.md](REAL_WORLD_VALIDATION.md) for wheel notes |
| Bootstrap paths | `deploy/bootstrap.sh` creates `var/` layout |

## Runtime inspection confidence

| Check | Status |
|-------|--------|
| Frozen 14-artifact lifecycle | Contract tests |
| `make runtime-help` discoverability | Stable sections |
| Empty/missing OUTPUT_DIR behavior | FAIL + operator actions in summaries |
| Strict mode (`--strict`) | Exit 1 on WARNING/FAIL — documented |
| Demo path without live nightly | `examples/demo_walkthrough/`, `demo_outputs/` |

## Release confidence

| Check | Status |
|-------|--------|
| Pre-tag gate | `make release-check` |
| Bundle compare | `make release-qualify` (not release-check) |
| Changelog + version SSOT | `newsroom/_version.py` = 1.0.0 stable |
| CI | `make ci-test` in GitHub Actions |

## Recovery confidence

| Check | Status |
|-------|--------|
| `validate-recovery` / `replay-runtime` | Documented in OPERATOR_QUICKSTART |
| DB restore | `backup_cli` — separate from recovery_report |
| Placeholder bundle in samples | Not for recovery validation |

## Maintenance confidence

| Check | Status |
|-------|--------|
| Maintenance-first mode | [MAINTENANCE_MODE.md](MAINTENANCE_MODE.md) |
| Issue/PR templates | `.github/` |
| Contract freeze guards | `tests/contracts/` |
| Dependency policy | [DEPENDENCY_POLICY.md](DEPENDENCY_POLICY.md) |

## Reproducibility confidence

| Check | Status |
|-------|--------|
| Deterministic JSON key order | Smoke + contract tests |
| Documented non-guarantees | [REPRODUCIBILITY.md](REPRODUCIBILITY.md) |
| `make quality` | contracts + smoke + lint + format |

## Gaps (accepted)

- No bundled “one command” production deploy — intentional (production-lite).
- No interactive TUI for failures — shell + JSON only.
- Nightly requires real credentials for full green path.

See [REAL_WORLD_VALIDATION.md](REAL_WORLD_VALIDATION.md) for walkthrough detail.
