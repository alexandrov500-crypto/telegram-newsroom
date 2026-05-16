# Operator workflow staging sign-off

Completion of [operator_workflow_validation.md](../live_validation/operator_workflow_validation.md) for production-lite rollout.

## Sign-off metadata

| Field | Value |
|-------|-------|
| Date | 2026-05-16 |
| Tier | Staging (code-path review + pending live bot session) |
| Operator | Pending named sign-off |

## Moderation fatigue

| Check | Result | Notes |
|-------|--------|-------|
| Approve/reject flows clear | **PASS** (code) | `approve_draft` / status transitions in `publish_service` |
| Long sessions | **PENDING** | Requires live bot session |
| Error messages | **PASS** (partial) | `PublishFlowOutcome` enum surfaces outcome to handlers |

**Pain points:** Admin flows split across bot handlers and DB state — operator must know draft id. Recommend pinning last draft id in ops notes.

## DLQ ergonomics

| Check | Result | Notes |
|-------|--------|-------|
| DLQ visible | **PASS** (code) | Worker `nack_dlq` + job queue metadata |
| Replay understood | **PASS** (docs) | Manual replay documented in runbooks |
| Terminal vs retry | **PASS** | `WORKER_RETRY_SAFE` + retry matrix |

## Recovery clarity

| Check | Result | Notes |
|-------|--------|-------|
| Stuck `publishing` | **PASS** (docs) | `reset_failed_draft_to_pending` in publish flow |
| Redis down | **PASS** (docs) | Strict vs fallback in publish_idempotency.md |
| Strict lock deny | **PASS** | `publish_lock_strict_denied` metric + diagnostics |

## Retry visibility

| Check | Result | Notes |
|-------|--------|-------|
| Worker logs | **PASS** | Structured `worker.job_retry` pattern |
| Storm warning | **PASS** | `retry_burst_window` in diagnostics |
| Safe mode | **PASS** | `WORKER_RETRY_SAFE=1` documented |

## Publish visibility

| Check | Result | Notes |
|-------|--------|-------|
| Chunk count logged | **PASS** | `publisher.chunks_sent` |
| Partial failure | **PASS** | Draft `FAILED`; no silent half-state in code |
| Cadence defer | **PASS** | `cadence_blocked_publish` + outcome |

## Operational discoverability

| Check | Result | Notes |
|-------|--------|-------|
| START_HERE | **PASS** | Live validation + ops links |
| `make ops-summary` | **PASS** | Target exists |
| Diagnostics | **PASS** | schema v2 JSON |

## Confusing flows (findings)

| Issue | Severity | Mitigation |
|-------|----------|------------|
| `FINALIZE_MISMATCH` — message on channel, DB wrong | HIGH | Manual reconcile; documented |
| Redis + strict lock must be paired for T2 | MEDIUM | staging checklist |
| Idempotency key optional in some paths | LOW | Use keys for worker publish jobs |

## Manual recovery friction

| Scenario | Score (1–5) | Notes |
|----------|-------------|-------|
| Republish after fail | 3 | Reset to pending works; partial chunk needs channel inspect |
| Session re-auth | 4 | Interactive 2FA not in MVP automation |
| OUTPUT_DIR inspect | 2 | `make runtime-index` well documented |

## UX friction (operator notes)

- Publish confirmation relies on bot UI — no separate web dashboard in T1.
- Retry count visible in logs, not consolidated UI (use diagnostics CLI).
- DRY_RUN easy to forget — verify env before staging publish session.

## Sign-off

| Item | Status |
|------|--------|
| Automated / code-path review | **PASS** |
| Live bot moderation session | **PENDING** |
| Named operator approval | **PENDING** |

When live session completes, add operator name and set status to **SIGNED**.
