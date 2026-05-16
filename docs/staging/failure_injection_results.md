# Failure injection results (bounded)

Controlled failure scenarios for staging sign-off. **Automated section** uses CI-safe mocks (no live Telegram). **Staging manual** section for operator with real `.env`.

## Automated proxy (executed 2026-05-16)

Command:

```bash
python3 -m pytest tests/staging/test_bounded_failure_injection.py -v --tb=short
```

| Scenario | Test | Result | Evidence |
|----------|------|--------|----------|
| Redis unavailable (strict) | `test_redis_unavailable_strict_denies_second_publish` | **PASS** | `publish_lock_strict_denied` ≥ 1 |
| Lock contention | `test_redis_contention_no_duplicate_lock_holder` | **PASS** | second acquire false; contention metric |
| Forced reconnect | `test_forced_reconnect_increments_metric` | **PASS** | `telethon_reconnects` ≥ 1 |
| Artificial publish retry | `test_publish_retry_increments_counter` | **PASS** | `publish_retries` ≥ 1 |
| Worker restart / safe retry | `test_worker_restart_safe_retry_order` | **PASS** | order `enqueue` → `ack` |

Related live/recovery suite:

```bash
make live-validation-validate
```

**27 passed**, 1 deselected — includes recovery, floodwait, publish integrity.

## Recovery assertions

| Requirement | Verified |
|-------------|----------|
| Deterministic recovery (mocked) | **YES** |
| No duplicate publish on contention | **YES** (second lock denied) |
| Diagnostics counters consistent | **YES** (metrics increment in tests) |
| Safe retry order | **YES** (`WORKER_RETRY_SAFE`) |

## Staging manual injection (operator)

Execute on staging host with `DRY_RUN=false` and **≤5 publishes** total budget.

| # | Injection | Steps | Expected | Actual |
|---|-----------|-------|----------|--------|
| 1 | Redis down (T2 only) | Stop Redis; attempt publish | strict deny or fallback per config | PENDING |
| 2 | Forced reconnect | Restart collector mid-tick | reconnect metric; recovery | PENDING |
| 3 | Publish retry | Transient network (if safe) | `publish_retries` increment; eventual success or FAILED | PENDING |
| 4 | Worker restart | Restart worker during pending job | safe re-enqueue; no duplicate | PENDING |

Post-injection: `make live-telegram-diagnostics` — confirm no HIGH findings.

## Diagnostics consistency

| Injection | Expected counter movement |
|-----------|---------------------------|
| Reconnect | `telethon_reconnects` ↑ |
| Publish retry | `publish_retries` ↑ |
| Lock contention | `publish_lock_contention` ↑ |
| Strict deny | `publish_lock_strict_denied` ↑ |

## Duplicate publish check

Automated lock tests: **no double acquire** on same `draft_id`.

Staging manual: inspect channel message ids after injection #4 — **PENDING**.

## Sign-off

| Layer | Status |
|-------|--------|
| CI bounded injection | **PASS** |
| Staging live injection | **PENDING** |
| No duplicate in CI | **PASS** |
