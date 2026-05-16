# Operational lifecycle

How the **live** service and **offline** operational tooling relate. This is a documentation view; it does not add runtime behavior.

## Live vs offline

- **Live:** `python -m app.main` (and optional workers) — continuous ingestion, pipeline ticks, publishes.
- **Offline / bounded:** CLIs under `tools/` and helpers under `utils/` — preflight, snapshots, bundles, comparison, qualification, static HTML, filesystem retention.

## Primary lifecycle (engineering order)

```
preflight
  ↓
runtime (startup validation, scheduler + bot + optional workers)
  ↓
benchmark + soak
  ↓
bundle (runtime_bundle.zip)
  ↓
regression (current zip vs baseline zip)
  ↓
qualification (read-only gate from bundles)
  ↓
dashboard (static HTML from bundle + JSON inputs)
  ↓
retention (artifact / JSON cleanup under configured roots)
```

`tools/runtime_ops.py nightly-check` executes the offline portion **after** `preflight` in a **fixed sequential order**; it does not supervise the live process.

## CI / nightly lifecycle

GitHub Actions mirrors a **short** path: install → preflight → frozen baseline bundle → `nightly-check` (short soak) → upload artifacts. See `docs/CI_CD.md`.

Release gate adds: pytest → same preflight/nightly chain → explicit `release_qualification.py --strict` (optionally `--require-regression-ok`).

## Where to read more

| Topic | Doc |
|-------|-----|
| Unified CLI | `docs/RUNTIME_OPS.md` |
| Preflight checks | `docs/RUNTIME_PREFLIGHT.md` |
| Bundle layout | `docs/RUNTIME_ARTIFACTS.md` |
| Regression math | `docs/RUNTIME_REGRESSION.md` |
| Qualification checks | `docs/RELEASE_QUALIFICATION.md` |
| Dashboard inputs | `docs/OPERATIONAL_DASHBOARD.md` |
| Retention rules | `docs/RUNTIME_RETENTION.md` |

## ADRs

- [ADR-003: No orchestration](ADR-003-no-orchestration-policy.md) — why there is no workflow engine between these steps.
- [ADR-004: Qualification semantics](ADR-004-release-qualification-semantics.md) — WARNING vs FAIL and strict modes.
