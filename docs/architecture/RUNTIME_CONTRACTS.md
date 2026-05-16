# Runtime operational contracts (frozen)

**Status:** Operationally stable as of ADR-015 (2026-05-15).  
**Governance model:** Complete — no further runtime governance layers planned.

This document freezes inspection interfaces for production-lite releases. It is not a policy engine or deployment platform.

## Operationally stable interfaces

The following are **stable** across patch releases unless a major version bump is declared:

| Surface | Contract |
|---------|----------|
| Artifact filenames | 14 files under `{output_dir}/runtime/` (see [RUNTIME_LAYOUT_REFERENCE.md](../RUNTIME_LAYOUT_REFERENCE.md)) |
| Lifecycle ordering | Generation order `1..14` (index last); reordering is **forbidden** |
| `schema_version` | Integer `1` for current generation; additive optional fields allowed |
| CLI commands | `health`, `verify-runtime`, `validate-recovery`, `replay-runtime`, `check-compatibility`, `audit-runtime`, `create-baseline`, `compare-baseline`, `inspect-capabilities`, `inspect-policy`, `runtime-index` |
| Runtime layout | `{output_dir}/runtime/*.json` plus optional `qualification.json`, `runtime_bundle.zip` at output root |
| Status enums | Tri-state: `OK`, `WARNING`, `FAIL`; incident: `NONE`, `WARNING`, `ERROR` |
| Category taxonomy | `health`, `reporting`, `verification`, `recovery`, `compatibility`, `audit`, `baseline`, `capabilities`, `policy` |

Canonical constants live in `observability/runtime_contracts.py` and are enforced by `tests/contracts/test_runtime_contracts.py`.

## Compatibility guarantees

- **Allowed:** new optional JSON fields; new optional artifacts (requires contract bump).
- **Breaking:** removing required fields; changing field types; renaming artifacts; changing lifecycle order; changing CLI command names.

## Experimental (not guaranteed)

- Optional baseline / drift workflows until baseline is created.
- `NEWSROOM_EXECUTION_MODE` / `--execution-mode` capability hints.
- `FUTURE_COMPATIBLE_SCHEMA_VERSIONS` in schema validation (warning-only).

## CLI inspection flags

| Flag | Behavior |
|------|----------|
| `--path` | Ops output directory or a file under `runtime/` |
| `--json` | Deterministic JSON (`sort_keys=True`) |
| `--strict` | Exit `1` on `WARNING` or `FAIL` |
| `--write` | Atomic latest-only write where supported |

Commands with `--write`: `validate-recovery`, `check-compatibility`, `inspect-capabilities`, `inspect-policy`, `runtime-index`.

## Runtime model

- **Runtime model:** `single-node`
- **Deployment profile:** `production-lite`

See [RUNTIME_MATURITY.md](RUNTIME_MATURITY.md) and [ADR-015](ADR-015-runtime-stabilization-and-contract-freeze.md).
