# Runtime ops unified CLI

This is **not** a workflow orchestration platform, scheduler, daemon, or CI engine. It is a **thin, deterministic, sequential** entry point that calls existing operational modules (`utils/runtime_preflight`, `tools/runtime_benchmark`, soak simulation, bundle, regression, qualification, dashboard, retention`) in a fixed order when you run `nightly-check`.

## Governance complete — stabilization phase

The **runtime governance model is complete** (ADR-001 through ADR-014). **No further runtime governance layers are planned.** Work now focuses on contract freeze, operator docs, and release discipline ([RUNTIME_CONTRACTS.md](architecture/RUNTIME_CONTRACTS.md), [RUNTIME_MATURITY.md](architecture/RUNTIME_MATURITY.md), [ADR-015](architecture/ADR-015-runtime-stabilization-and-contract-freeze.md)).

**Operator entrypoints:** `make runtime-help` · [OPERATOR_QUICKSTART.md](OPERATOR_QUICKSTART.md) · `python -m newsroom.cli runtime-index`

## Purpose

- One stable command surface for local development and optional nightly automation.
- Same-process execution: no background workers, no Redis requirement for the wrapper itself, no persisted workflow state.
- Human-readable summary or JSON on stdout for scripting.

## Commands

| Command | Behavior |
|--------|----------|
| `preflight` | Filesystem / settings / runtime JSON checks (Redis and disk checks stay off here; use `tools/runtime_preflight.py` if you need them). |
| `benchmark` | Operational benchmark snapshot → `ops_benchmark.json` under `--output-dir`. |
| `soak` | Bounded soak simulation → `soak_report.json` under `--runtime-dir`. |
| `bundle` | Zip runtime bundle → `runtime_bundle.zip` under `--output-dir`. |
| `regression` | Compare current bundle to `--baseline` zip (skipped if baseline or bundle missing). |
| `qualification` | Release qualification vs baseline (skipped if inputs missing). |
| `dashboard` | HTML dashboard from bundle / optional JSON reports. |
| `retention` | Filesystem retention pass over `--output-dir` (and optional `--reports-dir`). |
| `nightly-check` | Runs, in order: preflight → benchmark → soak → bundle → regression → qualification → dashboard → retention. |

## Flags

- `--runtime-dir` — `RUNTIME_STATE_DIR` (required for soak, bundle, benchmark).
- `--artifacts-dir`, `--reports-dir` — forwarded to preflight and retention where applicable.
- `--output-dir` — writable outputs (default: `./runtime_ops_output`).
- `--baseline` — baseline `runtime_bundle.zip` for regression and qualification.
- `--dry-run` — skips side-effectful steps that support it (benchmark, soak, bundle, regression, qualification, dashboard, retention); preflight still runs.
- `--strict` — exit non-zero when aggregate status is not `OK`, or when the CLI is invoked with `--strict` and JSON `status` is not `OK` (see below).
- `--short-soak` — shorter soak profile for `soak` and `nightly-check`.
- `--skip-retention` — skip retention during `nightly-check` only.
- `--json-output` — print the machine-readable report instead of the human summary.

## Local developer workflow

```bash
python tools/runtime_ops.py preflight --runtime-dir ./runtime_state
python tools/runtime_ops.py bundle --runtime-dir ./runtime_state --output-dir ./ops_out
```

## Nightly CI usage

Run the full linear pass from the repo root (paths are examples only):

```bash
python tools/runtime_ops.py nightly-check \
  --runtime-dir ./runtime_state \
  --output-dir ./ci_runtime_ops \
  --baseline ./baselines/runtime_bundle_baseline.zip \
  --short-soak \
  --strict
```

Use `--skip-retention` if the CI job should not prune artifact roots. Use `--json-output` to capture structured results in logs.

## Dry-run examples

```bash
python tools/runtime_ops.py nightly-check --runtime-dir ./runtime_state --output-dir ./ops_dry --dry-run --json-output
```

Expect most steps marked `SKIPPED` with `dry_run:skipped` warnings while preflight still evaluates configuration.

## Interpreting statuses

- **OK** — step completed without fatal issues.
- **WARNING** — soft failure or comparison drift; aggregate `nightly-check` may still be `WARNING` with `ok: true` unless `--strict` is used when interpreting exit codes.
- **FAIL** — hard failure; `nightly-check` sets `ok: false`.
- **SKIPPED** — missing inputs, `--dry-run`, or `--skip-retention` (retention only).

Human summary example:

```
Runtime ops summary

Command: nightly-check

[OK] preflight
[OK] benchmark
...
Overall: WARNING
```

## JSON report

Top-level fields include: `command`, `started_at`, `completed_at`, `status`, `executed_steps`, `skipped_steps`, `warnings`, `generated_artifacts`, `steps` (per-step detail), `ok`, and `preflight_ok` (mirrors `ok` for convenience).

After `nightly-check`, **latest-only** artifacts are written under `{output_dir}/runtime/` (atomic replace):

| File | Role |
|------|------|
| `health_snapshot.json` | Counters, pipeline status, failed nightly steps |
| `runtime_report.json` | Incident level, artifact inventory, domain `step_status`, bundle metadata |
| `runtime_manifest.json` | SHA256 checksums for tracked artifacts and bundle zip |
| `recovery_report.json` | Offline recovery validation summary |
| `compatibility_report.json` | Schema version compatibility summary |
| `qualification_history.json` | Bounded qualification trace (latest-first, max 20) |
| `audit_snapshot.json` | Aggregated audit summary over history |

**Runtime manifests are operational inspection artifacts, not deployment metadata.**

**Audit snapshots are operational inspection artifacts, not compliance archives.**

All runtime JSON artifacts include integer **`schema_version`** (currently `1`).

Inspect offline (not monitoring telemetry):

```bash
python -m newsroom.cli health --path ./runtime_ops_output
python -m newsroom.cli health --path ./runtime_ops_output --report
python -m newsroom.cli health --path ./runtime_ops_output --report --strict   # CI/shell: exit 1 if incident_level != NONE
make runtime-health OUTPUT_DIR=./runtime_ops_output
make runtime-report OUTPUT_DIR=./runtime_ops_output
```

### Runtime manifest lifecycle

1. `nightly-check` finishes health snapshot + runtime report.  
2. `build_runtime_manifest` hashes present artifacts (required always when on disk; optional only if present).  
3. `runtime_manifest.json` written with atomic replace (latest-only).  
4. Rebuild without re-running nightly: `make runtime-manifest OUTPUT_DIR=./runtime_ops_output`.

### Artifact verification semantics

| Artifact | Required | Missing → |
|----------|----------|-----------|
| `runtime/health_snapshot.json` | yes | FAIL |
| `runtime/runtime_report.json` | yes | FAIL |
| `qualification.json` | no | WARNING |
| `runtime_bundle.zip` | no | WARNING |
| `ops_benchmark.json` | no | WARNING |

Checksum mismatch on any manifest-listed file → FAIL.

```bash
python -m newsroom.cli verify-runtime --path ./runtime_ops_output
python -m newsroom.cli verify-runtime --path ./runtime_ops_output --json
python -m newsroom.cli verify-runtime --path ./runtime_ops_output --strict
make verify-runtime OUTPUT_DIR=./runtime_ops_output
make verify-runtime-json OUTPUT_DIR=./runtime_ops_output
```

### Reproducible packaging philosophy

Bundle zips use stable member ordering and fixed ZIP timestamps for lightweight reproducibility — not a full reproducible-build pipeline. See `utils/runtime_bundle.py` and [ADR-007](architecture/ADR-007-runtime-manifest-and-verification.md).

### Recovery validation lifecycle

1. Nightly ops writes manifest → `validate_runtime_recovery` runs (read-only).  
2. `recovery_report.json` written with atomic replace (latest-only).  
3. Checks: structure layout, JSON readability, manifest verification, bundle extractability (temp extract only).  
4. Re-validate anytime: `make validate-recovery OUTPUT_DIR=./runtime_ops_output`.

**Replay workflows are inspection-only and do not re-execute newsroom pipelines.**

| Recovery status | Typical cause |
|-----------------|----------------|
| **OK** | Structure, verification, and bundle (if present) valid |
| **WARNING** | Optional artifacts missing; verification WARNING |
| **FAIL** | Unreadable zip, missing required files, checksum mismatch, invalid structure |

```bash
python -m newsroom.cli validate-recovery --path ./runtime_ops_output
python -m newsroom.cli validate-recovery --path ./runtime_ops_output --json --strict
python -m newsroom.cli replay-runtime --path ./runtime_ops_output
make validate-recovery OUTPUT_DIR=./runtime_ops_output
make replay-runtime OUTPUT_DIR=./runtime_ops_output
```

### Runtime replay philosophy

`replay-runtime` extracts `runtime_bundle.zip` to a **temporary directory**, runs manifest verification and structure checks, prints a summary, and **removes the temp dir**. No ingestion, OpenAI, Telegram, DB writes, or pipeline execution.

See [ADR-008](architecture/ADR-008-runtime-recovery-and-replay-semantics.md).

### Runtime schema lifecycle

1. Each artifact writer sets `schema_version` to the current runtime schema (`1`).  
2. After recovery validation, nightly emits `compatibility_report.json`.  
3. Operators re-check anytime with `check-compatibility` (read-only).

**Compatibility validation is inspection-only and does not mutate artifacts.**

### Compatibility semantics

| Status | Cause |
|--------|--------|
| **OK** | All required artifacts present; `schema_version` supported |
| **WARNING** | Future-compatible version detected; optional gaps |
| **FAIL** | Unsupported version, missing required `schema_version`, malformed type |

```bash
python -m newsroom.cli check-compatibility --path ./runtime_ops_output
python -m newsroom.cli check-compatibility --path ./runtime_ops_output --json --strict
make check-compatibility OUTPUT_DIR=./runtime_ops_output
make check-compatibility-json OUTPUT_DIR=./runtime_ops_output
```

### Artifact evolution policy

**Minor-compatible (no schema bump required for readers):** adding optional fields; adding optional artifacts.

**Breaking (requires new `schema_version`):** removing required fields; changing field types; changing semantics.

No automatic migrations, rewrites, or upgrade tooling — validation only.

See [ADR-009](architecture/ADR-009-runtime-schema-and-compatibility-semantics.md).

### Qualification history lifecycle

1. Nightly ops completes compatibility check.  
2. One lightweight history entry appended (metadata only).  
3. `rotate_qualification_history` trims to `history_limit` (default 20), latest-first.  
4. `audit_snapshot.json` rebuilt from bounded history.

### Bounded audit semantics

- **Append-only** within the retention window; oldest entries dropped deterministically.  
- **No** raw logs, stack traces, article payloads, Telegram, or OpenAI content.  
- **Audit** aggregates `status_summary`, `recent_failures`, `recent_warnings` for shell inspection.

```bash
python -m newsroom.cli audit-runtime --path ./runtime_ops_output
python -m newsroom.cli audit-runtime --path ./runtime_ops_output --json
python -m newsroom.cli audit-runtime --path ./runtime_ops_output --strict
make audit-runtime OUTPUT_DIR=./runtime_ops_output
make audit-runtime-json OUTPUT_DIR=./runtime_ops_output
```

### Runtime audit philosophy

Audit is **operational traceability**, not compliance or analytics. Use it to see recent qualification trends and latest WARNING/FAIL signals — not as a long-term archive.

See [ADR-010](architecture/ADR-010-bounded-runtime-audit-and-history.md).

### Baseline lifecycle

1. After a known-good nightly run: `create-baseline` snapshots operational metadata to `runtime/runtime_baseline.json`.  
2. Subsequent runs (or `compare-baseline`) emit `runtime/drift_report.json`.  
3. Nightly ops auto-writes drift report when baseline exists.

**Baseline comparison is deterministic operational inspection, not anomaly analytics.**

### Drift detection semantics

| Drift status | Typical cause |
|--------------|----------------|
| **OK** | Baseline present; no significant drift |
| **WARNING** | Qualification downgrade, incident increase, duration delta > 15s, artifact version drift, no baseline |
| **FAIL** | Unreadable baseline, incompatible schema, missing required artifacts |

Fixed threshold: `RUNTIME_DURATION_WARNING_THRESHOLD_SEC = 15.0` (no adaptive/ML thresholds).

```bash
python -m newsroom.cli create-baseline --path ./runtime_ops_output
python -m newsroom.cli compare-baseline --path ./runtime_ops_output
python -m newsroom.cli compare-baseline --path ./runtime_ops_output --json --strict
make create-baseline OUTPUT_DIR=./runtime_ops_output
make compare-baseline OUTPUT_DIR=./runtime_ops_output
```

### Runtime comparison philosophy

Compare lightweight statuses and schema versions only — not logs, Telegram payloads, article content, or OpenAI responses.

See [ADR-011](architecture/ADR-011-runtime-baseline-and-drift-semantics.md).

### Deployment profile semantics

| Supported | Unsupported |
|-----------|-------------|
| `single-node` runtime model | distributed workers |
| `production-lite` profile | Kubernetes orchestration |
| manual, cron/systemd scheduling | multi-node runtime |
| docker-compose single-node | shared distributed state |
| offline runtime inspection | central telemetry platform |

**Capability profiles describe operational assumptions, not infrastructure automation.**

```bash
python -m newsroom.cli inspect-capabilities --path ./runtime_ops_output
python -m newsroom.cli inspect-capabilities --path ./runtime_ops_output --json --strict
make inspect-capabilities OUTPUT_DIR=./runtime_ops_output
```

### Runtime capability philosophy

Capabilities declare **what this ops stack guarantees** (bounded state, deterministic artifacts, shell-first) — not what infrastructure to provision. Validation is inspection-only.

See [ADR-012](architecture/ADR-012-runtime-capability-and-deployment-profile-semantics.md).

### Runtime policy philosophy

Policies document **architectural boundaries** (bounded retention, latest-only, single-node, offline inspection). They do not enforce changes at runtime.

**Runtime policies are operational inspection artifacts, not enforcement systems.**

### Operational guardrails

Required guardrails include: `no_distributed_coordination`, `no_background_daemons`, `no_unbounded_retention`, `no_runtime_mutation_during_validation`.

| Validation | Meaning |
|------------|---------|
| **OK** | Required policies true, guardrails present, constraints match constants |
| **WARNING** | Unknown optional policy/constraint |
| **FAIL** | Missing guardrail, invalid constraint, unsupported policy value, artifact cross-check violation |

```bash
python -m newsroom.cli inspect-policy --path ./runtime_ops_output
python -m newsroom.cli inspect-policy --path ./runtime_ops_output --json --strict
make inspect-policy OUTPUT_DIR=./runtime_ops_output
```

See [ADR-013](architecture/ADR-013-runtime-policy-and-guardrail-semantics.md).

### Unified runtime lifecycle

Deterministic generation order after `nightly-check`:

1. `health_snapshot.json` → 2. `runtime_report.json` → 3. `runtime_manifest.json` → 4. `recovery_report.json` → 5. `compatibility_report.json` → 6. `qualification_history.json` → 7. `audit_snapshot.json` → 8. `runtime_baseline.json` → 9. `drift_report.json` → 10. `runtime_capabilities.json` → 11. `capability_report.json` → 12. `runtime_policy.json` → 13. `policy_report.json` → 14. **`runtime_index.json`**

**Runtime index is a deterministic inspection catalog, not a workflow engine.**

### Runtime inspection entrypoint

```bash
python -m newsroom.cli runtime-index --path ./runtime_ops_output
python -m newsroom.cli runtime-index --path ./runtime_ops_output --json
python -m newsroom.cli runtime-index --path ./runtime_ops_output --strict
make runtime-index OUTPUT_DIR=./runtime_ops_output
```

### Artifact taxonomy

| Category | Artifacts |
|----------|-----------|
| health | health_snapshot |
| reporting | runtime_report, runtime_index |
| verification | runtime_manifest |
| recovery | recovery_report |
| compatibility | compatibility_report |
| audit | qualification_history, audit_snapshot |
| baseline | runtime_baseline, drift_report |
| capabilities | runtime_capabilities, capability_report |
| policy | runtime_policy, policy_report |

Governance artifact layers are **operationally complete**; prefer stabilization and release hardening over new inspection subsystems.

See [ADR-014](architecture/ADR-014-unified-runtime-index-and-consolidation.md).

See `docs/architecture/ADR-006-runtime-reporting-semantics.md` for incident rules.

## Makefile (optional)

Root `Makefile` targets: `make runtime-preflight`, `make runtime-nightly`, `make runtime-manifest`, `make verify-runtime`, `make validate-recovery`, `make replay-runtime`, `make check-compatibility`, `make audit-runtime`, `make create-baseline`, `make compare-baseline`, `make inspect-capabilities`, `make inspect-policy`, `make runtime-index` (wraps CLI with `RUNTIME_DIR` / `OUTPUT_DIR` overrides). Legacy aliases `runtime-ops-*` still work.
