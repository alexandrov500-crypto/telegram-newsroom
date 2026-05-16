# ADR-007: Runtime manifest and verification

Status: Accepted  
Date: 2026-05-15

Scope: `observability/runtime_manifest.py`, `observability/runtime_verify.py`, `runtime/runtime_manifest.json`, `newsroom.cli verify-runtime`, deterministic zip in `utils/runtime_bundle.py`.

## Context

Health snapshots and runtime reports give operators a human-oriented inspection view. For **integrity and reproducibility** we also need a machine-checkable manifest: which files exist, their sizes, and SHA256 digests — verifiable **offline** without a registry, signer, or orchestrator.

## Decision

- Emit **`{output_dir}/runtime/runtime_manifest.json`** after nightly health snapshot and runtime report (latest-only, atomic `os.replace`).
- Build manifests with **stdlib only**: deterministic JSON (`sort_keys`, stable top-level key order), SHA256 per tracked file, `schema_version: 1`.
- Classify artifacts as **required** (`health_snapshot.json`, `runtime_report.json`) vs **optional** (`qualification.json`, `runtime_bundle.zip`, `ops_benchmark.json`). Missing optional → verification WARNING; missing required or checksum mismatch → FAIL.
- Provide **`python -m newsroom.cli verify-runtime [--json] [--strict]`** for offline verification; `--strict` exits non-zero on WARNING or FAIL.
- Harden bundle zips with **sorted members** and **fixed ZIP timestamps** (1980-01-01) for lightweight reproducible archives.
- Treat manifests as **operational inspection artifacts, not deployment metadata**.

## Consequences

- **Positive:** Shell-first CI and postmortems can assert artifact integrity without external services; manifests are self-describing alongside reports.
- **Positive:** Re-run `make runtime-manifest` to refresh checksums after manual artifact fixes.
- **Negative:** `generated_at` is not part of reproducibility guarantees; only artifact bytes and stable ordering are.
- **Negative:** Optional artifacts omitted from manifest when absent — verification still flags them via `missing_optional`.

## Non-goals

- No artifact registry, package repository, or OCI/Docker registry integration.
- No deployment automation, signing infrastructure, GPG/PKI, or remote storage backends.
- No telemetry platform, orchestration framework, or historical manifest retention.
- No full reproducible-build system (compiler hashes, build-id pinning, etc.).
