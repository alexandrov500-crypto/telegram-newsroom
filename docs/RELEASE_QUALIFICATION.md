# Release qualification

## Purpose

Release qualification is a **read-only, deterministic** layer that turns existing runtime diagnostics into a single operational decision:

- `RELEASE_READY`: `true` or `false`
- `qualification_status`: `OK`, `WARNING`, or `FAIL`

It is **not** a deployment orchestrator, CI platform, stateful workflow engine, or telemetry stack. It consumes artifacts you already produce (`runtime_bundle.zip`, baseline zip, optional soak export) and applies bounded checks with explicit thresholds.

## Inputs

| Input | Source |
|-------|--------|
| Current bundle | `runtime_bundle.zip` (see [RUNTIME_ARTIFACTS.md](./RUNTIME_ARTIFACTS.md)) |
| Baseline bundle | Frozen reference zip (e.g. `runtime_baselines/stable_bundle.zip`) |
| Regression rows | From `utils.runtime_regression.run_regression_comparison` |
| Integrity | `integrity.json` inside the current bundle |
| Bounded state | `runtime_summary.json` → `bounded_state_report` |
| Soak | Optional `soak_report.json` (see [SOAK_TESTING.md](./SOAK_TESTING.md)) |
| Manifest | `manifest.json` → `missing_files` (e.g. optional soak not collected on host) |

No network, no Redis, no background services.

## Operational semantics

### Checks (fixed set)

1. **Bundle load** — fatal parse errors (`bad_zip`, `invalid_json`, missing zip, read failures) on current or baseline; non-fatal parse warnings; **critical files** present in the current zip.
2. **Integrity** — `integrity.json` issue lists empty when required; optional downgrade when `--no-require-integrity-clean`.
3. **Regression** — overall status from baseline vs current metric comparison ([RUNTIME_REGRESSION.md](./RUNTIME_REGRESSION.md)). `FAIL` fails qualification. `WARNING` is visible on the regression check; `release_ready` still allows warnings when `--allow-warning` is set.
4. **Queue health** — worst status among queue-related regression rows (`avg_oldest_pending_age_sec_sampled_kinds`, `queue_pressure_score`, `pending_jobs_total`). Any row `FAIL` fails qualification.
5. **Runtime state** — bounded counters in `bounded_state_report` compared with the same thresholds as regression (increase = worse, `ignore_missing=True`).
6. **Soak** — if `soak_report.json` exists: `bounded_report.ok` must be true and `warnings` must be empty. If `--require-soak` and the file is absent → check `FAIL`.

### `qualification_status`

- **FAIL** — any check has status `FAIL`.
- **WARNING** — no `FAIL`, at least one check has `WARNING`.
- **OK** — all checks `OK`.

### `RELEASE_READY`

- `false` if any check is `FAIL`, or any check is `WARNING` and `--allow-warning` was **not** passed.
- `true` otherwise.

### `--strict`

Exit code `1` unless `qualification_status` is `OK`, **and** the regression payload has no `warnings` (bundle-load / row notes from the regression helper). Use this when you want a green exit only when there is no residual noise in the comparison, even if `release_ready` could be true with `--allow-warning`.

### `--require-regression-ok`

Regression overall must be exactly `OK` (`WARNING` or `FAIL` fails the regression check regardless of `--allow-warning`).

### Critical files (current bundle)

- **Required:** `stability.json`, `benchmark.json`
- **Recommended:** `integrity.json`, `runtime_summary.json`, `manifest.json` — absence yields a **WARNING** on bundle load (graceful degradation for minimal zips).

## Interpreting OK / WARNING / FAIL

| Status | Meaning |
|--------|---------|
| OK | Check passed within policy. |
| WARNING | Actionable drift or missing recommended inputs; may still gate release depending on `--allow-warning`. |
| FAIL | Do not ship; fix bundle, integrity, regression, soak, or queue pressure first. |

Human summary (`--output-report`) lists checks in a stable **report** order: integrity → regression → queue → runtime state → soak → bundle load. Soak absent but optional shows `Soak: MISSING`.

## CLI

```bash
python tools/release_qualification.py \
  --runtime-bundle artifacts/runtime_bundle.zip \
  --baseline runtime_baselines/stable_bundle.zip
```

Useful flags:

| Flag | Role |
|------|------|
| `--warning-threshold-pct` / `--fail-threshold-pct` | Same meaning as regression compare (bounded state uses the same numbers). |
| `--allow-warning` | Allow `RELEASE_READY=true` when only checks are `WARNING`. |
| `--require-soak` | Fail if `soak_report.json` is missing or unhealthy. |
| `--require-integrity-clean` / `--no-require-integrity-clean` | Default: integrity issues fail; `--no-…` downgrades issues to `WARNING`. |
| `--require-regression-ok` | Disallow regression `WARNING`. |
| `--json-output PATH` | Stable JSON (`sort_keys=True`) for archiving. |
| `--output-report PATH` | Human-readable summary. |
| `--strict` | Stricter exit policy (see above). |

## JSON shape (`--json-output`)

Top-level keys (stable when written with `sort_keys=True`):

- `baseline_bundle`, `evaluated_at`, `runtime_bundle`
- `qualification_status`, `release_ready`
- `checks` — object keyed in **alphabetical** order (`bundle_load`, `integrity`, `queue_health`, …) so JSON matches sort-keys output
- `warnings`, `failures` — sorted lists of short diagnostic strings
- `threshold_config` — CLI policy echo

## Example nightly / release flow

This is **documentation of a typical shell sequence**, not an orchestrator built into the repo:

1. **Benchmark** — `tools/runtime_benchmark.py` (or your existing entrypoint).
2. **Soak** — `tools/soak_…` / profile run; write `soak_report.json` under the runtime dir when needed.
3. **Runtime artifact bundle** — `tools/build_runtime_artifact_bundle.py` → `runtime_bundle.zip`.
4. **Regression comparison** — `tools/compare_runtime_baseline.py --baseline … --current …` (optional standalone report).
5. **Release qualification** — `tools/release_qualification.py` → exit code + JSON/report for the gate.
6. **Upload artifacts** — store zip + qualification JSON in object storage or CI artifacts (outside this tool).

## Example qualification report

```
Release qualification summary

runtime_bundle: /build/runtime_bundle.zip
baseline_bundle: /baselines/stable_bundle.zip

Integrity: OK
Regression: WARNING
Queue health: OK
Runtime state: OK
Soak: MISSING
Bundle load: OK

Qualification status: WARNING
RELEASE_READY: true
```

(With default flags, `RELEASE_READY` would be `false` unless `--allow-warning` is passed.)

## Implementation

- Library: `utils/release_qualification.py`
- CLI: `tools/release_qualification.py`
- Tests: `tests/runtime/test_release_qualification.py`
