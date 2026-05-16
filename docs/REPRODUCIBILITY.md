# Reproducibility

What this repository **guarantees** for operators and CI, and what is **intentionally out of scope**. Runtime governance is frozen; this document covers tooling and artifact semantics only.

## Deterministic JSON philosophy

Runtime inspection artifacts use:

- Fixed top-level **key order** (`KEY_ORDER` tuples in `observability/*.py`)
- `schema_version: 1` with documented additive rules (ADR-009)
- `json.dumps(..., sort_keys=True)` where nested objects require stable ordering
- Atomic write: `.tmp` + `os.replace`

**Goal:** meaningful `diff` and contract tests without ad hoc normalization scripts.

## Stable ZIP semantics

`utils/runtime_bundle.py` builds archives with:

- Sorted member paths
- Fixed ZIP timestamp (`1980-01-01`) for deterministic bytes

**Goal:** regression and qualification compare bundle hashes across runs when inputs are identical.

## Runtime ordering guarantees

- **Lifecycle:** artifacts generated in order `1..14`; `runtime_index.json` last (ADR-014).
- **Manifest:** artifact entries sorted by name.
- **Index:** `generation_order` matches frozen lifecycle tuple.

Enforced by `tests/contracts/test_runtime_contracts.py` and smoke tests.

## Contract tests

| Suite | Guards |
|-------|--------|
| `tests/contracts/test_runtime_contracts.py` | Filenames, lifecycle, CLI registry, Makefile help sections |
| `tests/contracts/test_release_layout.py` | Deploy templates, samples, release docs |
| `tests/contracts/test_docs_navigation.py` | START_HERE links, demo scripts, docs-map |

Run: `make contracts` or `make ci-test`.

## Reproducible operator workflows

Given the **same** `OUTPUT_DIR` inputs (existing nightly outputs, unchanged files on disk):

- `make verify-runtime` → same checksum conclusions
- `make runtime-index` → same catalog structure (status may reflect file presence)
- `make check-compatibility` → same schema classification
- `python -m newsroom.cli … --strict` → same exit code policy

Pinned dev tools: `requirements-dev.txt` (`pytest`, `ruff`).

## Guaranteed

| Area | Guarantee |
|------|-----------|
| Artifact filenames | Frozen set of 14 under `runtime/` |
| Lifecycle order | `1..14` fixed |
| JSON key order | Per-artifact `KEY_ORDER` |
| Schema version | `1` supported; contract tests enforce |
| ZIP member order | Sorted paths, fixed timestamp |
| CLI command registry | 11 inspection commands frozen |
| Contract test suite | Deterministic pass/fail in CI |

## Not guaranteed

| Area | Why |
|------|-----|
| `generated_at` timestamps | Wall-clock at write time |
| Identical nightly bytes run-to-run | Benchmark/soak inputs differ |
| OpenAI outputs | Model nondeterminism |
| Network / Telegram behavior | External systems |
| Live DB contents | Editorial state changes |
| Identical RSS / duration across hosts | Environment load |

## Limitations

Reproducibility targets **offline inspection** and **repository CI**, not full pipeline replay. For operational comparison, use baselines (`create-baseline` / `compare-baseline`) understanding duration thresholds are approximate.

## Related

- [REPOSITORY_STANDARDS.md](REPOSITORY_STANDARDS.md)
- [architecture/RUNTIME_CONTRACTS.md](architecture/RUNTIME_CONTRACTS.md)
- [architecture/ADR-016-repository-reproducibility-and-maintenance.md](architecture/ADR-016-repository-reproducibility-and-maintenance.md)
- [examples/reproducible_runtime_workflow.md](examples/reproducible_runtime_workflow.md)
