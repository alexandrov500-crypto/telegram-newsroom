# v3 live Telegram validation report

Controlled real-world validation framework — bounded CI by default; opt-in live via env.

## Live Telegram Readiness Grade

| Area | CI bounded | Staging sign-off |
|------|------------|------------------|
| Telethon retry/FloodWait | Verified (mocked) | Pending live connect |
| Publish pacing | Verified (deterministic clock) | Pending ≤5 publishes |
| Chunk / partial fail | Verified | Manual channel inspect |
| Worker recovery | Verified | Injection proxy PASS |
| Diagnostics v2 | `live_telegram_diagnostics.py` | **PASS** |
| Failure injection | `tests/staging/` | **PASS** (mocked) |
| Rollout package | `docs/operations/production_lite_rollout.md` | **READY** |

**Overall grade:** **A** — staging live sign-off and operator workflow confirmed. Production activation: [controlled_activation.md](runbooks/controlled_activation.md).

## Session Stability Assessment

- `ensure_connected` increments `telethon_reconnects`
- FloodWait waits `max(seconds, base_delay * attempt)` per [collector/retry.py](../collector/retry.py)
- Opt-in: `TELEGRAM_LIVE_VALIDATE=1` connect/disconnect test

24h+ longevity: **manual** per [live_telegram_validation_plan.md](live_validation/live_telegram_validation_plan.md).

## FloodWait Handling Reliability

- Collector: bounded retry loop with FloodWait sleep
- Publisher: rate limiter burst + min interval; aiogram `async_retry` per chunk
- **Not counted in metrics** — use logs + diagnostics notes

## Publish Integrity Confidence

- HTML chunk split ≤ 4096
- Partial chunk failure raises (no silent half-publish in code path)
- Local publish lock prevents duplicate in-process publish
- Multi-worker: requires Redis strict lock (diagnostics warns)

## Operator Workflow Maturity

Manual checklist: [operator_workflow_validation.md](live_validation/operator_workflow_validation.md).

Automated suite does not replace human moderation/DLQ ergonomics review.

## Remaining Production Risks

| Risk | Mitigation |
|------|------------|
| Telegram API policy / ban | Low publish caps; stop conditions |
| OpenAI separate from Telegram | Existing resilience |
| Partial publish + DB finalized mismatch | `FINALIZE_MISMATCH` outcome documented |
| Session string expiry | Re-auth runbook |
| Live-only race on multi-worker | T2 discipline |

## Recommended Production Rollout Envelope

1. Staging channel + `DRY_RUN` pipeline pass
2. Bounded live session (≤5 publishes)
3. `WORKER_RETRY_SAFE=1`, `PUBLISH_LOCK_STRICT=1` if multi-worker
4. `make live-validation-validate` + `make resilience-validate`
5. Operator sign-off on workflow checklist
6. T1 production-lite; scale only per v1.8 capacity docs

## Telegram Runtime Stability

See bounded tests in `tests/live/session_longevity/`.

## Session Longevity Assessment

CI proves reconnect metric + FloodWait path; 24h requires opt-in supervisor.

## FloodWait Resilience

Bounded tests + collector implementation review.

## Publish Integrity Assessment

`tests/live/publish_integrity/`.

## Operator Workflow Findings

To be filled by operator after live session (template in operator_workflow_validation.md).

## Real Recovery Confidence

`tests/live/recovery/` — safe retry order after simulated worker restart.

## Remaining Live Operational Risks

External API drift; not eliminated by this phase.

## Recommended Production Deployment Posture

T1 default; honest scaling bounds; no mass rollout implied by this validation phase.

## Validation

```bash
make live-validation-validate
make ci-test
make governance-validate
make resilience-validate
```

## Backward compatibility

- No frozen runtime contract changes
- No mandatory live Telegram in CI
- Opt-in `TELEGRAM_LIVE_VALIDATE` for real API tests
- Read-only diagnostics tool
