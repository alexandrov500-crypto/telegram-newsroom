# ADR-009: Runtime schema and compatibility semantics

Status: Accepted  
Date: 2026-05-15

Scope: `observability/runtime_schema.py`, `runtime/compatibility_report.json`, `schema_version` on runtime artifacts, `newsroom.cli check-compatibility`.

## Context

Runtime ops emits multiple JSON artifacts (health snapshot, report, manifest, recovery report). Operators need **forward-compatible evolution** rules and **offline validation** that a directory matches supported schema versions — without Alembic, automatic migrations, or a registry service.

## Decision

- Add integer **`schema_version`** to all runtime JSON artifacts (current version `1`).
- Maintain an in-code **`SUPPORTED_SCHEMA_VERSIONS`** list and optional **`FUTURE_COMPATIBLE_VERSIONS`** for WARNING-only forward detection.
- Emit **`{output_dir}/runtime/compatibility_report.json`** after nightly recovery validation (latest-only, atomic replace).
- Expose **`python -m newsroom.cli check-compatibility [--json] [--strict]`** — inspection-only; **does not mutate artifacts**.
- Document **evolution policy** (minor-compatible vs breaking changes) in ops/architecture docs; **no migration framework**.

**Compatibility validation is inspection-only and does not mutate artifacts.**

## Consequences

- **Positive:** CI and shells can gate on `compatibility_status`; schema drift is explicit in one report.
- **Positive:** Future schema bumps can warn before support lands via `FUTURE_COMPATIBLE_VERSIONS`.
- **Negative:** No automatic upgrade path for old artifact trees; operators re-run nightly or tolerate WARNING until refreshed.
- **Negative:** Cross-artifact semantic compatibility (field meaning) is not proven — only version integers and presence.

## Non-goals

- Migration framework, Alembic-like tooling, automatic artifact rewrites or upgrade CLIs.
- Schema registry service, protobuf/thrift/avro, distributed compatibility negotiation.
- Background compatibility daemons, version synchronization service, runtime mutation during validation.
