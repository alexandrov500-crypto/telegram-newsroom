# ADR-014: Unified runtime index and consolidation

Status: Accepted  
Date: 2026-05-15

Scope: `observability/runtime_index.py`, `runtime/runtime_index.json`, `newsroom.cli runtime-index`.

## Context

Runtime ops now emits many inspection JSON files (health, report, manifest, recovery, compatibility, audit, baseline, drift, capabilities, policy). Operators need a **single deterministic catalog** — not another governance layer, orchestrator, or registry service.

## Decision

- Emit **`runtime_index.json`** as the **table of contents** for all runtime artifacts with fixed categories, generation order, and schema versions when present.
- Validate index offline: unique names, lifecycle order, required presence, known categories.
- CLI **`runtime-index [--json] [--strict] [--write]`** as the unified inspection entrypoint.
- Write index **last** in `nightly-check` (generation order 14).
- Freeze further governance artifact layers unless a strong new requirement emerges; treat runtime governance model as **operationally complete**.

**Runtime index is a deterministic inspection catalog, not a workflow engine.**

## Lifecycle order (deterministic)

1. health_snapshot → 2. runtime_report → 3. runtime_manifest → 4. recovery_report → 5. compatibility_report → 6. qualification_history → 7. audit_snapshot → 8. runtime_baseline → 9. drift_report → 10. runtime_capabilities → 11. capability_report → 12. runtime_policy → 13. policy_report → 14. runtime_index.

## Consequences

- **Positive:** One file answers “what exists, in what order, under which category?”
- **Positive:** CI/shell can gate on `index_status` after nightly.
- **Negative:** Index does not encode dependencies or execution — order is documentary only.
- **Negative:** Self-referential index entry appears only after write completes.

## Non-goals

- Orchestration graph, dependency resolver, DAG engine, workflow scheduler.
- Plugin registry, distributed runtime registry, service discovery, dynamic artifact loading.
- Runtime graph execution, central governance platform.
