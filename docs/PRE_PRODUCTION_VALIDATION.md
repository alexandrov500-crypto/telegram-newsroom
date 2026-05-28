# Pre-production validation (FINAL)

Operational plan before public Telegram channel launch. **Priority: stability → observability → safety → automation → features.**

## Architecture audit (current)

| Layer | Location | Status |
|-------|----------|--------|
| Decision engine | `app/state/pipeline_decision_engine.py` | Production-grade |
| Execution wrapper + registry | `app/state/pipeline_execution_*` | Enforced |
| Async orchestrator | `app/runtime/task_orchestrator.py` | Single `create_task` path |
| Polling supervisor | `app/telegram_polling.py` | Backoff + probe + conflict |
| Telethon retries | `collector/retry.py` | Exp backoff, flood wait |
| Ops control plane | `app/ops/control_plane/` | emergency_halt, rate limits |
| Public launch gates | `app/editorial/*` staging, sanitizer, trust | Active |
| Operator CLI | `python3 -m newsroom.cli newsroom` | Human dashboard |
| Health | `GET /health` via `app/dependency_state.py` | Extended async + pipeline |

## Highest-risk gaps (addressed incrementally)

1. **Telegram DC unreachable** — collect tick blocks on Telethon connect (no wall-clock cap) → **Phase 1**
2. **Health blind to in-flight collect** — operator cannot see stalled collect → **Phase 1**
3. **Operator dashboard SQL** — `updated_at` on drafts → **Phase 1 fix**
4. **Publish idempotency under retry** — existing lock; add explicit audit trail → Phase 2
5. **Pre-publish quality gate** — partial in sanitizer; extend heuristics → Phase 3
6. **Comment-driven tuning** — partial via `draft_extras` / config; formal hooks → Phase 4

## Phased implementation

### Phase 1 — Telegram reliability + health (this release)

- Resilient Telethon connect (timeout, structured logs)
- Collect cycle guard (stall detection, optional wall-clock timeout)
- `telegram_connectivity` block on `/health`
- Operator dashboard: network, polling, collect-in-progress

**Rollback:** unset `COLLECT_CYCLE_TIMEOUT_SEC=0`, revert env; no schema changes.

**Validate:**

```bash
curl -s http://127.0.0.1:8080/health | python3 -c "import json,sys; d=json.load(sys.stdin); print(d.get('telegram_connectivity'))"
python3 -m newsroom.cli newsroom
python3 -m pytest tests/test_collect_cycle_guard.py tests/test_telegram_connectivity_snapshot.py -q
```

### Phase 2 — Editorial safety + publish audit

- Publish audit trail events
- Idempotency test suite
- Re-approval after edit

### Phase 3 — Pre-publish quality control

- Empty summary, markdown, semantic dup threshold (config-driven)

### Phase 4 — Operator feedback / tuning layer

- `config/editorial_tuning.yaml` + hot-reload hooks (no hardcoded rules)

### Phase 5 — Pre-production test mode flags

- `PRE_PRODUCTION_VALIDATION_MODE`, shadow publish, panic stop (reuse `OPS_EMERGENCY_HALT`)

## Environment flags (Phase 1)

```bash
TELETHON_CONNECT_TIMEOUT_SEC=25
COLLECT_CYCLE_TIMEOUT_SEC=300      # 0 = disabled
COLLECT_CYCLE_STALL_WARN_SEC=120
PRE_PRODUCTION_VALIDATION_MODE=true  # stricter defaults when unset per-field
```

## Sign-off checklist

See `docs/PUBLIC_LAUNCH_CHECKLIST.md` plus:

- [ ] `/health` → `telegram_connectivity.dc_reachable` not persistently false
- [ ] First pipeline tick completes or logs explicit `collect_cycle.stalled` / timeout
- [ ] No duplicate bot polling (VPS container stopped)
- [ ] `burnin_monitor` GO for 7 days
