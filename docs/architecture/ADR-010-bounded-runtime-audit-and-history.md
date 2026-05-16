# ADR-010: Bounded runtime audit and qualification history

Status: Accepted  
Date: 2026-05-15

Scope: `observability/runtime_history.py`, `runtime/qualification_history.json`, `runtime/audit_snapshot.json`, `newsroom.cli audit-runtime`.

## Context

Runtime ops already emits latest-only inspection artifacts (health, report, manifest, recovery, compatibility). Operators need **recent qualification traceability** and a **bounded audit view** without an event platform, warehouse, or compliance archive.

## Decision

- Maintain **`qualification_history.json`** with append-only semantics inside a fixed window (`history_limit` default 20, latest-first).
- Emit **`audit_snapshot.json`** aggregating recent OK/WARNING/FAIL counts, latest statuses, and lightweight warning/failure strings.
- History entries capture only operational metadata (status fields, duration, timestamp) — no logs, payloads, or Telegram/OpenAI content.
- Integrate history append + audit rebuild at the end of `nightly-check` (atomic writes).
- Expose **`python -m newsroom.cli audit-runtime [--json] [--strict]`** for offline inspection; `--strict` exits non-zero when latest qualification or audit status is not OK.

**Audit snapshots are operational inspection artifacts, not compliance archives.**

## Consequences

- **Positive:** Shell-first trend visibility; deterministic bounded JSON; no unbounded disk growth.
- **Positive:** Append + rotate is idempotent within the retention window.
- **Negative:** History older than N runs is dropped — not suitable for long-term audit retention.
- **Negative:** Cross-run analytics remain out of scope (counts only, no time-series DB).

## Non-goals

- Event sourcing, telemetry warehouse, analytics platform, ELK/OpenSearch.
- Compliance archive, long-term retention backend, distributed audit service.
- Background audit daemons, raw log ingestion, time-series databases, observability platforms.
