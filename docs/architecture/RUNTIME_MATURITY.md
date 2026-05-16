# Runtime operational maturity

## Operational freeze (v1.0.0)

> **Runtime governance and inspection model are considered operationally frozen as of v1.0.0.**
>
> Further work is **stabilization over expansion**: compatibility-first maintenance, bounded complexity, and operator ergonomics — not new governance artifacts or inspection subsystems.
>
> See [STABILITY_GUARANTEES.md](../STABILITY_GUARANTEES.md) and [MAINTENANCE_POLICY.md](../MAINTENANCE_POLICY.md).

## Maturity scope

The **runtime governance model is complete** (ADR-001 through ADR-015). Further work focuses on **stabilization**, **operator ergonomics**, and **release discipline** — not new inspection subsystems.

## Supported operational model

- Single-node, production-lite deployment.
- Bounded JSON artifacts under `{output_dir}/runtime/`.
- Sequential `nightly-check` wrapper (`tools/runtime_ops.py`) — not an orchestrator.
- Shell-first inspection via `python -m newsroom.cli` and `make` targets.
- Offline validation only; no enforcement daemon.

## Production-lite guarantees

- Deterministic artifact generation order (frozen).
- Latest-only writes (`os.replace`) for runtime JSON.
- Fixed schema version `1` with documented evolution rules.
- Unified index (`runtime_index.json`) as inspection entrypoint.

## Cognitive compactness principles

- One directory (`runtime/`) for inspection JSON.
- One CLI catalog (`runtime-index`, `make runtime-help`).
- Tri-state statuses (`OK` / `WARNING` / `FAIL`) across layers.
- No platform-scale complexity by design.

## Explicit non-goals

The system **intentionally avoids** platform-scale complexity:

- No orchestration graph or workflow engine for ops artifacts.
- No telemetry warehouse, compliance archive, or policy engine.
- No Kubernetes/distributed runtime as a first-class target.
- No automatic remediation or runtime mutation during validation.
- No further governance artifact layers without a major contract revision.

## Bounded complexity philosophy

Add capability at the **application** layer (ingest, publish, editorial) sparingly. Keep **ops inspection** thin, frozen, and grep-friendly. When in doubt, document and test contracts instead of adding new reports.

See [RUNTIME_CONTRACTS.md](RUNTIME_CONTRACTS.md) and [ADR-015](ADR-015-runtime-stabilization-and-contract-freeze.md).
