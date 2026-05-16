# CI/CD (lightweight, deterministic)

Philosophy and tradeoffs: **`docs/architecture/SYSTEM_OVERVIEW.md`**, **`docs/architecture/ADR-003-no-orchestration-policy.md`**. Volatile-field CI skips: **`docs/architecture/ADR-004-release-qualification-semantics.md`** + `docs/CI_CD.md` § *Volatile metrics*.

This repository uses **GitHub Actions** as a *bounded operational CI layer* — not a deployment platform, not Kubernetes, and not a SaaS observability stack. Workflows are **pinned to Python 3.12**, use **pip caching**, and avoid secrets by default via committed placeholder env (`.github/ci-minimal.env`).

## Workflow overview

| Workflow | File | When | Purpose |
|----------|------|------|---------|
| Tests | `.github/workflows/tests.yml` | push/PR | Fast pytest subset (`tests/runtime`, `tests/smoke`), fail-fast |
| Nightly runtime | `.github/workflows/nightly-runtime.yml` | schedule + `workflow_dispatch` | Preflight → bundle baseline → `runtime_ops nightly-check` → artifact upload |
| Release check | `.github/workflows/release-check.yml` | push/PR + manual | Tests + preflight + nightly (strict) + `release_qualification.py --strict` gate |

## Lifecycle (release-check, conceptual)

```
tests (pytest)
  ↓
preflight (tools/runtime_preflight.py --strict)
  ↓
runtime_ops nightly-check (--short-soak --strict)
  ↓
qualification gate (tools/release_qualification.py --strict --require-regression-ok)
  ↓
dashboard (produced inside nightly output dir)
  ↓
artifact upload (stable name: ops-release-ci-<run_id>-<run_number>/)
```

## Nightly semantics

- **Short soak only** — `nightly-check` uses `--short-soak` (bounded ticks/time in `utils/runtime_ops`).
- **No long soak** — no multi-hour daemon soak in CI.
- **No secrets by default** — `.github/ci-minimal.env` supplies non-production placeholders sufficient for `load_settings()` and preflight (still **never** use these values in real deployments).
- **Deterministic baseline** — a **frozen copy** of the runtime JSON tree under `ci-artifacts/runtime-baseline` is zipped once as `runtime_bundle_ci_baseline.zip`. The **live** tree `ci-artifacts/runtime-live` is used for soak/bundle so regression compares evolving bundle vs immutable baseline (avoids false drift when soak rewrites `soak_report.json` in-place).

## Artifacts

Uploaded directories use **predictable names** (no random UUIDs):

- **Nightly:** `ops-ci-${{ github.run_id }}-${{ github.run_number }}` containing copies of:
  - `runtime_bundle.zip`, `operational_dashboard.html`, `qualification.json`, `regression.json`, `retention.json`, `ops_benchmark.json` (when present), `ops_summary.json` (nightly JSON stdout on scheduled workflow).
- **Release check:** `ops-release-ci-${{ github.run_id }}-${{ github.run_number }}` plus `qualification_gate.json` / `qualification_gate.txt`.

## Strict vs non-strict

- **`runtime_ops.py --strict`:** fails the job if aggregate status is not `OK` (warnings fail). See `docs/RUNTIME_OPS.md`.
- **`release_qualification.py --strict`:** fails if qualification is not `OK` and bundle/regression checks are not clean enough for the chosen flags. Release workflow also passes **`--require-regression-ok`** so regression `overall_status` must be `OK`.

## Volatile metrics in CI (deterministic)

Synthetic baseline bundles are built **before** soak appends timeline data to the live tree. Comparing bundles would otherwise mark `timeline_bytes` as a 0→N **FAIL** (100% increase). CI sets `NEWSROOM_REGRESSION_SKIP_METRICS=timeline_bytes` in `.github/ci-minimal.env` so regression/qualification stay **signal-bearing** for other metrics while ignoring this known volatile field. Qualification also compares `bounded_state_report.timeline_events`; CI sets `NEWSROOM_QUALIFICATION_SKIP_RUNTIME_KEYS=timeline_events,timeline_file_bytes` for the same reason. Unset these variables locally to restore full strictness.

## Local reproduction

From repo root (bash):

```bash
make ci-test
make ci-nightly
# Full gate (tests + preflight + nightly + qualification):
bash scripts/release_check.sh
```

Or mirror CI manually:

```bash
set -a && source .github/ci-minimal.env && set +a
export PYTHONPATH="$PWD"
mkdir -p ci-artifacts/runtime-baseline ci-artifacts/runtime-live ci-artifacts/baseline-stage
# seed JSON (see workflow YAML)
make ci-nightly
```

## Operational expectations

- **Tests workflow** should finish in **under a few minutes** on `ubuntu-latest`.
- **Nightly** budget **~25 minutes** wall clock (hard timeout in workflow); typical run is much shorter.
- **Release check** budget **~30 minutes**; dominated by pytest + short soak + zip I/O.

## Troubleshooting

| Symptom | Likely cause | What to do |
|---------|--------------|------------|
| `load_settings` / `OPENAI_API_KEY is required` | env not sourced | `set -a; source .github/ci-minimal.env; set +a` |
| Preflight `FAIL` on SQLite | `DATABASE_URL` path parent missing | `mkdir -p ci-artifacts` before running |
| Regression `WARNING` after soak | baseline not isolated | ensure baseline zip built from `runtime-baseline` only (see workflows) |
| `release_qualification` exit 2 | `--strict` + regression warnings | inspect `qualification_gate.txt` artifact; compare `regression.json` |
| Workflow cancelled | `cancel-in-progress` concurrency | re-run latest commit; avoid duplicate branch workflows |

## Makefile targets

| Target | Meaning |
|--------|---------|
| `make ci-test` | Same pytest slice as CI |
| `make ci-nightly` | `scripts/nightly_runtime.sh` |
| `make ci-release-check` | `scripts/release_check.sh` |
| `make release-check` | v1.0.0 readiness (contracts, smoke, quality, packaging) |
| `make release-qualify` | Bundle qualification (requires `RUNTIME_BUNDLE` + `BASELINE`) |

## Related docs

- `docs/RUNTIME_OPS.md` — unified ops CLI.
- `docs/RELEASE_QUALIFICATION.md` — qualification semantics.
- `docs/OPERATIONS.md` — operator commands outside CI.
