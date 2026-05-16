# Stability guarantees (v1.0.0)

What maintainers treat as stable for the **1.0.x** line. Application editorial features may evolve under separate review; **runtime governance is frozen**.

## Guaranteed stable

| Area | Guarantee |
|------|-----------|
| Runtime artifact filenames | 14 files under `runtime/` — frozen |
| Lifecycle generation order | `1..14`, index last |
| `schema_version` | `1` for inspection artifacts |
| Tri-state statuses | `OK` / `WARNING` / `FAIL` |
| Inspection CLI commands | 11 commands — frozen registry |
| JSON key order | Per-module `KEY_ORDER` tuples |
| Makefile inspection targets | `runtime-help`, `runtime-index`, etc. |

## Additive-compatible (1.0.x)

- Optional new **fields** inside existing JSON objects at `schema_version: 1` (ADR-009 rules)
- Documentation, examples, contract tests
- Application-layer features that do not add runtime governance artifacts

## Intentionally unstable

| Area | Notes |
|------|-------|
| `generated_at` timestamps | Wall clock |
| OpenAI model outputs | Nondeterministic |
| Benchmark / soak metrics | Environment-dependent |
| Baseline drift warnings | Experimental until baselined |
| `app.versioning` live-state schema | Separate from inspection `runtime/*.json` |

## Unsupported extensions

- New `runtime/*.json` artifact types
- New governance inspection modules implying enforcement
- Orchestration graphs, policy engines, telemetry warehouses
- CLI commands beyond the frozen registry
- Breaking renames of artifacts, categories, or lifecycle order

## Runtime contracts

Frozen in [architecture/RUNTIME_CONTRACTS.md](architecture/RUNTIME_CONTRACTS.md) and `observability/runtime_contracts.py`. Changes require ADR + contract test updates + major version discussion.

## Schema policy

- Inspection artifacts: `schema_version: 1` only (supported set `(1,)`).
- Forward-compatible detection of version `2` may WARN — not a commitment to support v2 in 1.0.x.

## CLI stability

- `python -m newsroom.cli <command>` dispatch frozen.
- Flags: `--path`, `--json`, `--strict`, `--write` per command registry.
- Console scripts in `pyproject.toml` mirror commands — do not remove without major release.

## Governance freeze

**Runtime governance and inspection model are operationally frozen as of v1.0.0.** Stabilization over expansion; compatibility-first maintenance.

See [architecture/RUNTIME_MATURITY.md](architecture/RUNTIME_MATURITY.md), [MAINTENANCE_POLICY.md](MAINTENANCE_POLICY.md).
