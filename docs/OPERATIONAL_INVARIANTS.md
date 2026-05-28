# Operational invariants (frozen)

These rules must hold in production. Violations are logged as `invariant.violation`; **CRITICAL** config violations fail startup.

## Runtime ownership

| ID | Invariant | Enforcement |
|----|-----------|-------------|
| INV-001 | Only one active Telegram poller per `BOT_TOKEN` | `RUNTIME_NODE_ROLE` + startup validation |
| INV-002 | Control plane does not run full scheduler by default | `node_role` profile |
| INV-012 | Execution lease must not be stale on worker | heartbeat check |

## Pipeline

| ID | Invariant | Enforcement |
|----|-----------|-------------|
| INV-020 | Pipeline tick must terminate (no infinite `running`) | `pipeline_ticks` + stuck detection |
| — | Scheduler tick records `finished_at` | `finish_persisted_tick` |

## Publishing

| ID | Invariant | Enforcement |
|----|-----------|-------------|
| — | Publish must be idempotent | Redis/memory idempotency + publish journal |
| — | Every publish attempt has audit log | `publish_journal` JSONL |
| INV-003 | Retries bounded (`FAILED_DRAFT_MAX_RETRIES` ≤ 20) | config validation |
| INV-011 | Maintenance halts publish only (pipeline may continue) | `auto_maintenance.json` + `publish_allowed` |

## Draft lifecycle

| ID | Invariant | Enforcement |
|----|-----------|-------------|
| — | Status transitions are monotonic (no escape from terminal) | `db/draft_lifecycle.py` |
| — | FAILED → PENDING only for operator/retry | `reset_failed_draft_to_pending` |

## Observability

| ID | Invariant | Enforcement |
|----|-----------|-------------|
| INV-010 | No polling conflict while healthy | `conflict_detected` on `/health` |
| — | `correlation_id` on pipeline tick and draft extras | `operational_context` |

## Code

- Checks: `app/reliability/invariants.py`
- Startup: `assert_startup_invariants()` after `validate_settings_for_launch()`
- Heartbeat: `run_heartbeat_invariant_checks()`
