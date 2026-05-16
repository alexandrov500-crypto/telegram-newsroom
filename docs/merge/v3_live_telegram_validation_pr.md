# PR: v3 live Telegram operational validation

## Summary

Adds bounded, CI-safe live Telegram validation for the production-lite newsroom: mocked resilience tests, opt-in real API checks, read-only diagnostics, operational runbooks, and merge-ready governance—without frozen runtime contract changes or default-on live Telegram traffic.

## Bounded live validation strategy

- Default CI runs `tests/live` with `-m "not live_telegram"` (mocked Telethon, publisher, locks, recovery).
- Real Telegram connect/publish requires `TELEGRAM_LIVE_VALIDATE=1` and operator governance caps (≤5 publishes, staging channel).
- No load-test theater; no spam patterns.

## Opt-in Telegram execution

- Pytest marker `live_telegram` on optional tests (`test_live_session_optional.py`).
- `make ci-test` does not execute live tests.
- Live validation plan defines stop conditions and rollback expectations.

## Operational governance model

- `docs/live_validation/live_validation_governance.md` — cadence, abuse prevention, operator safety.
- `docs/operations/retry_error_matrix.md` — transient vs terminal errors, escalation table.
- `docs/operations/publish_idempotency.md` — guaranteed vs non-guaranteed behaviors.

## Recovery guarantees

- Worker safe retry ordering tested (`WORKER_RETRY_SAFE`).
- Session recovery tests (corrupt session path, auth terminal, reconnect metrics, limiter reset).
- Publish lock contention → `ALREADY_HANDLED` (no duplicate send in code path).
- Partial chunk failure documented; `FINALIZE_MISMATCH` for DB/channel drift.

## Retry semantics

- Collector: FloodWait + RPC/OS with bounded attempts (`collector/retry.py`).
- Publisher: per-chunk `async_retry` with `publish_retries` metric.
- Documented in retry matrix; architecture flow in `live_validation_runtime_flow.md`.

## Diagnostics safety guarantees

- `tools/live_telegram_diagnostics.py`: read-only, `no_telegram_api_calls`, schema v2.
- Aggregates in-process metrics and reliability buffers only.
- `--strict` fails on HIGH findings (config safety, session instability, retry storm).

## CI isolation strategy

| Gate | Scope |
|------|--------|
| `make ci-test` | runtime + smoke + contracts (no live_telegram) |
| `make live-validation-validate` | tests/live + ops contracts + diagnostics CLI |
| `make governance-validate` | release readiness |
| `make resilience-validate` | chaos + soak |

## Test plan

- [ ] `make live-validation-validate`
- [ ] `make ci-test`
- [ ] `make governance-validate`
- [ ] `make resilience-validate`
- [ ] Confirm no changes under frozen `runtime/*.json` sample contracts
- [ ] Optional staging: `TELEGRAM_LIVE_VALIDATE=1 pytest tests/live -m live_telegram`

## Backward compatibility

- Frozen runtime JSON artifacts unchanged.
- New metric `telethon_flood_waits` defaults to 0.
- `publish_retries` now incremented on publisher retry (previously defined but unused).
