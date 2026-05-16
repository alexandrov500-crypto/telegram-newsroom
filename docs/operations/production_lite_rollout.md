# Production-lite rollout plan (v3.1)

Single-node bounded deployment path after staging sign-off. **Not** a scale-out or multi-region plan.

## Overview

```mermaid
flowchart LR
    T0[T0 DRY_RUN] --> T1[T1 bounded publish]
    T1 --> T2[T2 optional multi-worker]
```

## Phase T0 — Observation only

| Aspect | Setting |
|--------|---------|
| `DRY_RUN` | `true` |
| Workers | Single worker or scheduler-only smoke |
| Publish | Disabled (dry-run skip) |
| Redis | Optional off |
| Channel | Staging acceptable |

**Enable criteria**

- `make ci-test` + `make live-validation-validate` + `make governance-validate` green
- `staging_environment_verify.py` no HIGH findings
- Diagnostics baseline captured

**Monitoring**

- `make live-telegram-diagnostics` daily
- `make ops-summary` after pipeline ticks
- Log review: no unhandled tracebacks

**Operational limits**

- Zero Telegram publishes to audience channels
- Collector may run on limited sources if configured

**Rollback triggers**

- Unexpected Telegram API calls while `DRY_RUN=true`
- Runtime inspection FAIL

**Rollback**

- Stop processes; fix env; no data loss expected

---

## Phase T1 — Bounded production-lite

| Aspect | Setting |
|--------|---------|
| `DRY_RUN` | `false` |
| Publish cap | **≤5/day** initial; raise only via ADR/operator |
| Workers | **Single** publisher path |
| `PUBLISH_LOCK_STRICT` | `false` if no Redis |
| Operator | Single named operator; manual oversight |

**Enable criteria**

- Staging sign-off **A** ([live_staging_signoff.md](../staging/live_staging_signoff.md))
- Operator workflow signed
- `TARGET_CHANNEL_ID` verified non-production OR accepted production-lite channel with cap
- Failure injection proxy tests green

**Monitoring**

- Diagnostics after each publish day
- `publish_failures`, `publish_retries`, `telethon_flood_waits`
- Timeline events in `RUNTIME_STATE_DIR`

**Operational limits**

- ≤5 publishes/day (week 1)
- Respect cadence + rate limiter settings
- No second concurrent publisher process

**Rollback triggers**

- Any duplicate post
- `FINALIZE_MISMATCH`
- Sustained HIGH diagnostics
- FloodWait loop

**Rollback**

1. `DRY_RUN=true`
2. Stop scheduler/worker
3. Mark stuck drafts failed → pending per runbook
4. Revert to T0 for 24h observation

---

## Phase T2 — Optional multi-worker

| Aspect | Setting |
|--------|---------|
| `REDIS_ENABLED` | `true` |
| `PUBLISH_LOCK_STRICT` | `true` |
| Workers | >1 only with lock discipline |
| Monitoring | Elevated — contention + retry storm |

**Enable criteria**

- T1 stable ≥7 days
- Redis HA acceptable for ops team
- Chaos lock tests pass on staging config

**Monitoring**

- `publish_lock_contention`, `publish_lock_strict_denied`
- `retry_burst_window` vs `RUNTIME_RETRY_STORM_COUNT`
- Redis latency / reconnect storm runbook

**Operational limits**

- Same publish/day cap until operator raises
- No autonomous remediation bots

**Rollback triggers**

- Lock contention without publish completion
- Redis fallback events in production
- Duplicate publish suspicion

**Rollback**

- Scale to single worker (T1 config)
- `PUBLISH_LOCK_STRICT=1` keep but stop extra workers
- See [REDIS_RECONNECT_STORM.md](../runbooks/REDIS_RECONNECT_STORM.md)

## Cross-phase requirements

| Requirement | T0 | T1 | T2 |
|-------------|----|----|-----|
| Frozen runtime contracts | ✓ | ✓ | ✓ |
| No schema changes | ✓ | ✓ | ✓ |
| Governance caps | ✓ | ✓ | ✓ |
| Rollback documented | ✓ | ✓ | ✓ |

## References

- [retry_error_matrix.md](retry_error_matrix.md)
- [publish_idempotency.md](publish_idempotency.md)
- [observability_validation.md](observability_validation.md)
- [../releases/v3.1-production-lite.md](../releases/v3.1-production-lite.md)
