# ADR-008: Runtime recovery and replay semantics

Status: Accepted  
Date: 2026-05-15

Scope: `observability/runtime_recovery.py`, `runtime/recovery_report.json`, `newsroom.cli validate-recovery`, `newsroom.cli replay-runtime`.

## Context

Runtime manifests and verification prove **integrity** of on-disk ops artifacts. Operators also need **recovery validation**: can a portable ops directory (and its bundle zip) be understood and trusted offline — without running ingestion, OpenAI, Telegram, or DB restore?

## Decision

- Emit **`{output_dir}/runtime/recovery_report.json`** after nightly manifest write (latest-only, atomic replace).
- Implement **read-only** recovery checks: structure layout, JSON readability, manifest verification integration, bundle extractability (temp dir only).
- Expose **`python -m newsroom.cli validate-recovery [--json] [--strict]`** for offline validation; `--strict` exits non-zero on WARNING or FAIL.
- Expose **`python -m newsroom.cli replay-runtime`** as **inspection-only replay**: extract bundle to a temporary directory, verify manifest and structure, print summary, delete temp — **no pipeline execution**.
- Recovery statuses: **OK**, **WARNING**, **FAIL** with explicit rules (FAIL for unreadable bundle, missing required files, checksum mismatch, invalid structure; WARNING for optional gaps or missing manifest with recoverable structure).

**Replay workflows are inspection-only and do not re-execute newsroom pipelines.**

## Consequences

- **Positive:** Portable ops directories are self-checking for postmortems and CI without orchestration.
- **Positive:** Replay proves bundle extractability without mutating production runtime state.
- **Negative:** Recovery validation does not prove logical correctness of pipeline data — only structural and checksum integrity.
- **Negative:** Bundle inner content is not fully cross-checked against outer manifest beyond extract + inner `manifest.json` presence during replay.

## Non-goals

- No orchestration engine, workflow replay engine, or distributed recovery.
- No database restore, snapshot replication, Kubernetes jobs, or async recovery workers.
- No background recovery daemons, remote recovery storage, automatic remediation, or self-healing.
- No execution replay (ingestion, OpenAI, Telegram publish, DB mutation, network I/O).
