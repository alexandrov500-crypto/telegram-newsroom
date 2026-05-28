# Phase 3 — Stability freeze

## Implementation plan

| Step | Deliverable | Status |
|------|-------------|--------|
| 1 | `docs/OPERATIONAL_INVARIANTS.md` + `app/reliability/invariants.py` | done |
| 2 | `docs/PUBLIC_INTERFACES.md` + `docs/EDITORIAL_LAYER.md` | done |
| 3 | `tests/reliability/` + `make reliability-test` | done |
| 4 | Chaos-lite tests (in-process) | done |
| 5 | `observability/canonical_metrics.py` | done |
| 6 | Production runbooks (`docs/runbooks/production/`) | done |
| 7 | `ops/alert_discipline.py` cooldowns | done |
| 8 | Stricter `startup_validation` | done |
| 9 | `docs/TECHNICAL_DEBT_FREEZE.md` | done |

## Reliability matrix

| Scenario | Test module | Auto-recovery |
|----------|-------------|---------------|
| Telegram timeout | `test_publish_retryable` | failed_drafts retry |
| OpenAI outage | `test_openai_circuit` (existing) | fallback summarizer |
| DB locked | `test_retryable_classification` | retry + backoff |
| Scheduler stuck | `test_stuck_tick_detection` | mark stale + alert |
| Duplicate poller | `test_control_polling_invariant` | startup fail |
| Partial publish failure | `test_draft_lifecycle` | idempotency journal |
| Stale execution lease | `test_execution_lease` | clear stale |
| Maintenance mode | `test_publish_halted` | publish_allowed false |
| Config dual-worker | `test_startup_control_worker` | startup fail |

## Safe-freeze strategy

1. Tag release `v3-stability-freeze` after green `make reliability-test`.
2. Only editorial PRs allowed without runtime review.
3. Runtime changes require invariant + reliability test update.

## Long-term maintenance model

- **Daily:** `make newsroom-status` (2 min)
- **Weekly:** `make reliability-test`, check `/ops/panel.json`
- **Deploy:** `make deploy-safe` only
- **Monthly:** review `TECHNICAL_DEBT_FREEZE.md`, rotate secrets

## Commands

```bash
make reliability-test
make newsroom-panel
bash scripts/newsroom maintenance status
```
