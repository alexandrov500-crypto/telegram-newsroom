# System overview

Production-lite Telegram newsroom: **ingest → editorial → publish** with **bounded** on-disk diagnostics and **deterministic** offline tooling. This document states intent; it does not replace code or runbooks.

## High-level architecture

```
Telegram sources
    ↓
ingestion (Telethon collector)
    ↓
deduplication / clustering (scheduler + lexical pre-cluster + OpenAI)
    ↓
editorial workflow (policy, relevance, cadence — heuristics + prompts)
    ↓
publish pipeline (admin bot, publish_service, optional workers)
    ↓
runtime diagnostics (JSON under RUNTIME_STATE_DIR, metrics, integrity)
    ↓
qualification / dashboard / retention (offline tools on artifacts)
```

## Runtime components (live)

| Area | Role |
|------|------|
| `app/` | Entrypoint, settings, health/ops HTTP, startup validation |
| `scheduler/` | Pipeline tick, coordination with `pipeline_lock` |
| `collector/` | Telethon ingestion |
| `ai/` | OpenAI calls, prompt registry |
| `bot/` | Admin moderation UX |
| `publisher/` | Channel publish path, locks, rate limits |
| `db/` | Persistence (SQLite default, Postgres optional) |
| `worker/`, `workers/` | Optional queue + worker processes when Redis is enabled |
| `editorial/`, `dashboard/`, `observability/` | Decisioning and read-only views of state |

## Operational layers (offline / bounded)

| Layer | Typical entry | Doc |
|-------|----------------|-----|
| Preflight | `tools/runtime_preflight.py` | `RUNTIME_PREFLIGHT.md` |
| Benchmark | `tools/runtime_benchmark.py` / `runtime_ops benchmark` | evidence reports |
| Soak | `tools/soak_runner.py` / `runtime_ops soak` | `SOAK_TESTING.md` |
| Bundle | `tools/build_runtime_artifact_bundle.py` / `runtime_ops bundle` | `RUNTIME_ARTIFACTS.md` |
| Regression | `tools/compare_runtime_baseline.py` / `runtime_ops regression` | `RUNTIME_REGRESSION.md` |
| Qualification | `tools/release_qualification.py` / `runtime_ops qualification` | `RELEASE_QUALIFICATION.md` |
| Dashboard | `tools/build_operational_dashboard.py` / `runtime_ops dashboard` | `OPERATIONAL_DASHBOARD.md` |
| Retention | `tools/runtime_retention.py` / `runtime_ops retention` | `RUNTIME_RETENTION.md` |
| Unified runner | `tools/runtime_ops.py` | `RUNTIME_OPS.md` |
| Health snapshot | `python -m newsroom.cli health` | `observability/health_snapshot.py` |
| Runtime report | `python -m newsroom.cli health --report` | `observability/runtime_report.py` |
| Runtime manifest | `make runtime-manifest` / nightly tail | `observability/runtime_manifest.py` |
| Artifact verification | `python -m newsroom.cli verify-runtime` | `observability/runtime_verify.py` |
| Recovery validation | `python -m newsroom.cli validate-recovery` | `observability/runtime_recovery.py` |
| Replay inspection | `python -m newsroom.cli replay-runtime` | `observability/runtime_recovery.py` |
| Schema compatibility | `python -m newsroom.cli check-compatibility` | `observability/runtime_schema.py` |
| Bounded audit | `python -m newsroom.cli audit-runtime` | `observability/runtime_history.py` |
| Baseline / drift | `create-baseline`, `compare-baseline` | `observability/runtime_baseline.py` |
| Capability profile | `inspect-capabilities` | `observability/runtime_capabilities.py` |
| Runtime policy | `inspect-policy` | `observability/runtime_policy.py` |
| Runtime index | `runtime-index` | `observability/runtime_index.py` |

## Bounded-state philosophy

Operational truth lives in **small, inspectable artifacts** (JSON + zip), not in an ever-growing proprietary telemetry backend. See [ADR-001](ADR-001-bounded-runtime-state.md).

## Reliability model (realistic)

- **At-least-once** semantics where queues exist; **single-writer** discipline for SQLite.
- **Degraded** behavior when Redis is absent or flaky (documented; not hidden).
- **Human-in-the-loop** publishing for MVP safety (`DRY_RUN`, admin approvals).

## Deterministic tooling principles

- Same inputs → same **sorted-key JSON** and stable CLI exit semantics where enforced.
- No hidden network calls in preflight/bundle/qualification paths by default.
- CI pins Python and uses explicit artifact names (see `docs/CI_CD.md`).

## Production-lite philosophy

Optimize for **one skilled operator** on a **single VPS or small Compose stack**: readable logs, copy-pastable commands, artifacts that fit in tickets.

## Runtime invariants

- **Runtime state is bounded** — caps, compaction, and retention prevent unbounded JSON growth ([ADR-001](ADR-001-bounded-runtime-state.md)).
- **Operational artifacts are replaceable** — each nightly run can overwrite `runtime/health_snapshot.json`, bundles, and reports; only the latest snapshot is authoritative.
- **Pipelines are restart-safe** — no workflow engine state; a failed step does not corrupt prior artifacts beyond explicit writes.
- **Health snapshots are deterministic** — stable JSON key order, sorted fields, atomic single-file replace (`observability/health_snapshot.py`).
- **Qualification inputs are immutable** — gates read frozen `runtime_bundle.zip` files, not live process memory ([ADR-004](ADR-004-release-qualification-semantics.md)).
- **Runtime inspection must work offline** — `python -m newsroom.cli health` and static HTML dashboards require no running service.

## Failure domains

| Domain | Impact | Bounded consequence | Recovery |
|--------|--------|---------------------|----------|
| **Ingestion failure** | No new raw posts for a tick | Backlog may grow; counters stall in benchmark snapshot | Fix Telethon session/network; retry next pipeline tick; check `SOURCE_CHANNELS` |
| **Summarization failure** | No new drafts from clusters | OpenAI errors in metrics; soak/benchmark show retry counters | Validate API key/limits; reduce `MAX_CLUSTER_POSTS`; inspect `openai.*` logs |
| **Telegram publish failure** | Drafts not reaching target channel | `publish_failures` counter rises; admin may see stuck `publishing` | Bot admin rights, `TARGET_CHANNEL_ID`, flood limits; manual DB status fix if needed |
| **Retention / packaging failure** | Artifact dirs grow or bundle step fails | Nightly marks `bundle`/`retention` FAIL; health snapshot lists `failed_steps` | Free disk; fix permissions on `output_dir`; re-run `runtime_ops bundle` |
| **Qualification failure** | Release gate blocks promote | `qualification_status` FAIL in health snapshot; CI exit non-zero | Compare `regression.json` / `qualification.json`; refresh baseline zip if intentional drift |

## Health snapshot and runtime report (latest-only)

After `runtime_ops nightly-check`, the runner writes (atomic replace):

| File | Purpose |
|------|---------|
| `{output_dir}/runtime/health_snapshot.json` | Headline counters and pipeline status |
| `{output_dir}/runtime/runtime_report.json` | Inspection bundle: incident level, artifact inventory, step_status |
| `{output_dir}/runtime/runtime_manifest.json` | SHA256 manifest of tracked artifacts + bundle metadata |

**Runtime manifests are operational inspection artifacts, not deployment metadata.** Reports and manifests are **operational inspection artifacts**, not monitoring telemetry. No time-series backend, no alerting.

```bash
python -m newsroom.cli health --path ./runtime_ops_output
python -m newsroom.cli health --path ./runtime_ops_output --report
python -m newsroom.cli health --path ./runtime_ops_output --report --strict   # exit 1 if incident_level != NONE
```

### Runtime report lifecycle

1. Nightly ops completes → health snapshot written.  
2. Runtime report builder reads snapshot + ops output directory.  
3. Artifact inventory booleans and `runtime_bundle` metadata (size, mtime) recorded.  
4. `build_incident_summary` sets `incident_level` (see [ADR-006](ADR-006-runtime-reporting-semantics.md)).  
5. Operator or CI inspects via CLI; optional `--strict` for shell gates.

### Incident semantics (summary)

| Level | Typical cause |
|-------|----------------|
| `NONE` | All checks green, expected artifacts present |
| `WARNING` | Missing optional artifact, `qualification_status == WARNING`, or soft pipeline WARNING |
| `ERROR` | `failed_steps` non-empty, `qualification_status == FAIL`, or pipeline FAIL |

### Artifact inventory philosophy

Inventory answers “what files exist on disk for this run?” — not “what did the metrics server say?” Missing zip/JSON files produce **warnings** in the report and may raise incident level to WARNING; they do not abort the writer.

## Runtime manifest and verification (latest-only)

After health snapshot and runtime report, nightly ops writes `{output_dir}/runtime/runtime_manifest.json` with stable JSON key order and per-file SHA256 checksums.

### Runtime manifest lifecycle

1. Nightly ops completes → health snapshot and runtime report written.  
2. Manifest builder scans required and present optional artifacts under `output_dir`.  
3. Checksums and sizes recorded; bundle zip summarized under `bundle`.  
4. Atomic replace writes `runtime_manifest.json` (latest-only).  
5. Operators verify offline via `python -m newsroom.cli verify-runtime` or `make verify-runtime`.

### Artifact verification semantics

| Class | Files | Missing behavior |
|-------|--------|------------------|
| **Required** | `runtime/health_snapshot.json`, `runtime/runtime_report.json` | Verification **FAIL** |
| **Optional** | `qualification.json`, `runtime_bundle.zip`, `ops_benchmark.json` | Verification **WARNING** (listed in `missing_optional`) |
| **Checksum** | Any artifact listed in manifest | Mismatch → **FAIL** |

`--strict` on the verify CLI exits non-zero on WARNING or FAIL for shell/CI gates.

### Reproducible packaging philosophy

`utils/runtime_bundle.write_runtime_bundle` uses sorted archive members and fixed ZIP timestamps (1980-01-01) for **lightweight deterministic packaging** — not a full reproducible-build system. Goal: comparable zip layout across runs with identical inputs, for regression and integrity checks.

See [ADR-007](ADR-007-runtime-manifest-and-verification.md).

## Recovery validation and replay (latest-only)

After manifest write, nightly ops emits `{output_dir}/runtime/recovery_report.json`. Validation is **read-only**: no restore, no pipeline replay, no network, no DB mutation.

### Recovery validation lifecycle

1. Verify manifest checksums (`runtime_verify`).  
2. Validate `runtime/` structure and JSON readability.  
3. Test bundle zip extractability (private temp dir during validation).  
4. Emit `recovery_report.json` with `recovery_status` ∈ {OK, WARNING, FAIL}.

### Offline recovery semantics

| Check | FAIL | WARNING |
|-------|------|---------|
| Required runtime JSON | missing / invalid | — |
| Manifest verification | checksum mismatch, missing required | missing manifest with partial structure; optional gaps |
| Bundle zip | corrupt / unreadable | absent (optional) |

### Runtime replay philosophy

`replay-runtime` unpacks the bundle to a temp directory, re-runs verification and structure checks, prints a summary, and deletes the temp directory. **Replay workflows are inspection-only and do not re-execute newsroom pipelines.**

See [ADR-008](ADR-008-runtime-recovery-and-replay-semantics.md).

## Runtime schema and compatibility (latest-only)

Each runtime JSON artifact carries **`schema_version`** (integer, positive). Nightly ops writes `compatibility_report.json` after recovery validation.

### Runtime schema lifecycle

1. Writers stamp `schema_version: 1` on health snapshot, report, manifest, recovery report.  
2. `check_runtime_compatibility` reads artifacts (no mutation).  
3. Report lists per-file versions vs `supported_versions`.  
4. CLI/Makefile for offline re-checks.

### Compatibility semantics

| Status | Typical cause |
|--------|----------------|
| **OK** | Versions in `supported_versions` |
| **WARNING** | Future-compatible version (e.g. `2` in `FUTURE_COMPATIBLE_VERSIONS`) |
| **FAIL** | Unsupported version, missing `schema_version`, malformed type |

**Compatibility validation is inspection-only and does not mutate artifacts.**

### Artifact evolution policy

- **Minor-compatible:** optional fields/artifacts.  
- **Breaking:** remove required fields, change types or semantics → bump `schema_version`.  
- **No** migration platform, automatic upgrades, or artifact rewriting.

See [ADR-009](ADR-009-runtime-schema-and-compatibility-semantics.md).

## Bounded qualification history and audit (latest-only)

`qualification_history.json` stores up to **20** lightweight entries (latest-first). `audit_snapshot.json` summarizes recent OK/WARNING/FAIL counts and latest statuses.

### Qualification history lifecycle

1. Nightly ops writes inspection artifacts.  
2. `append_qualification_history` adds one metadata row.  
3. Rotation drops oldest entries beyond `history_limit`.  
4. `build_audit_snapshot` refreshes audit summary (atomic replace).

### Bounded audit semantics

**Audit snapshots are operational inspection artifacts, not compliance archives.** No event stream, warehouse, or long-term retention — only bounded operational traceability for single-node ops.

See [ADR-010](ADR-010-bounded-runtime-audit-and-history.md).

## Runtime baseline and drift (latest-only)

`runtime_baseline.json` captures a known-good metadata snapshot; `drift_report.json` records comparison using **fixed thresholds** (15s duration delta).

### Baseline lifecycle

1. Operator runs `create-baseline` after a good ops pass.  
2. `compare-baseline` (or nightly tail) diffs current artifacts vs baseline.  
3. Drift report lists warnings/failures — inspection-only, no mutation.

**Baseline comparison is deterministic operational inspection, not anomaly analytics.**

See [ADR-011](ADR-011-runtime-baseline-and-drift-semantics.md).

## Runtime capability profile (latest-only)

`runtime_capabilities.json` states deployment assumptions; `capability_report.json` validates them offline.

**Capability profiles describe operational assumptions, not infrastructure automation.**

### Supported vs unsupported execution models

- **Supported:** single-node, production-lite, manual/cron/systemd, docker-compose single-node, offline inspection.  
- **Unsupported:** distributed workers, Kubernetes, multi-node runtime, shared distributed state, central telemetry.

See [ADR-012](ADR-012-runtime-capability-and-deployment-profile-semantics.md).

## Runtime policy and guardrails (latest-only)

`runtime_policy.json` states operational policies and guardrails; `policy_report.json` validates them offline.

**Runtime policies are operational inspection artifacts, not enforcement systems.**

### Architectural boundary semantics

Supported domains: bounded retention, deterministic artifacts, latest-only files, offline inspection, single-node runtime, shell-first ops. Explicitly **not** supported: distributed execution, orchestration engines, dynamic scaling, telemetry platforms, mutation during validation.

See [ADR-013](ADR-013-runtime-policy-and-guardrail-semantics.md).

## Unified runtime index (consolidation)

`runtime_index.json` is the **single inspection catalog** for all runtime JSON artifacts: names, paths, categories, schema versions, and documented generation order.

**Runtime index is a deterministic inspection catalog, not a workflow engine.** The governance model is considered operationally complete (ADR-001–014); further work should focus on stabilization and release hardening.

See [ADR-014](ADR-014-unified-runtime-index-and-consolidation.md).

## Stabilization and contract freeze

The runtime governance stack is **operationally complete**. Further changes should follow [RUNTIME_CONTRACTS.md](RUNTIME_CONTRACTS.md) and [ADR-015](ADR-015-runtime-stabilization-and-contract-freeze.md): no new governance artifacts; focus on release hardening and operator ergonomics (`make runtime-help`, [OPERATOR_QUICKSTART.md](../OPERATOR_QUICKSTART.md)).

## Non-goals (system-wide)

- No distributed orchestration layer for the newsroom pipeline.
- No realtime enterprise observability UI as a product requirement.
- No mandated microservice split; optional workers are a **scale-up** path, not the default story.
- No in-repo “infra abstraction” that hides where SQLite and `RUNTIME_STATE_DIR` actually live.

## ADRs

See [architecture/README.md](README.md) for the ADR index.
