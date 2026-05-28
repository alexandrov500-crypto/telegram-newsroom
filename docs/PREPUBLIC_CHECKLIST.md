# Pre-public launch checklist

Controlled public exposure only after all sections are signed.

## 1. Deterministic pipeline contract

- [ ] `bash scripts/burnin-check.sh` → **PASS** (exit 0)
- [ ] Last 3+ tail ticks: `status` ∈ {ok, reject}, `terminal_state` present
- [ ] Zero `aborted_draft` in log tail
- [ ] Zero `PIPELINE_FATAL_BREAK` in log tail
- [ ] No `running` ticks older than `MAX_TICK_RUNTIME_SEC` (default 1200s)

```bash
python3 tools/burnin_validation.py check --log logs/local-run.log --min-ticks 3
python3 -c "import asyncio; from app.config import load_settings; from app.reliability.stale_tick_recovery import reconcile_stale_pipeline_ticks; asyncio.run(reconcile_stale_pipeline_ticks(load_settings(), source='manual'))"
```

## 2. Output / golden tick

- [ ] `make golden-check` — at least one golden tick in window
- [ ] `committed_draft` in last 24h (target: `MIN_DRAFTS_PER_24H_TARGET`)
- [ ] Manual publish: `/preview_channel <id>` matches channel post
- [ ] No JSON/debug leakage on channel

```bash
make golden-check
export BURNIN_SOFT_GOVERNANCE=true   # staging only — relaxes cooldown/suppress
export BURNIN_OPENAI_ALWAYS_FALLBACK=true  # if quota unstable
```

## 3. Burn-in duration (3–7 days)

Daily: `docs/BURN_IN_OPERATIONS.md` table + `var/runtime/burnin_snapshot.json`

| Day | committed_draft | committed_reject | publishes | notes |
|-----|-----------------|------------------|-----------|-------|
| D0 | | | | |
| … | | | | |

## 4. Degraded modes

| Condition | Expected behavior |
|-----------|-------------------|
| OpenAI 429 | `committed_reject` or fallback draft (if `BURNIN_OPENAI_ALWAYS_FALLBACK` / starvation) |
| Collect slow | tick completes with terminal_state, no orphan `running` |
| Restart | stale ticks finalized on startup; no duplicate publish |

## 5. Rollback criteria

Stop public exposure if:

- Any tick ends without `terminal_state`
- `aborted_draft` reappears in logs
- Sanitizer/lock violation on channel
- Stuck `running` ticks > 2× `MAX_TICK_RUNTIME_SEC` without auto-finalize

```bash
bash scripts/stop_local_newsroom.sh
# PUBLISH_QUALITY_GATE_STRICT=false
# unset BURNIN_SOFT_GOVERNANCE
```

## 6. Operator recovery

1. `curl -s http://127.0.0.1:8080/health | python3 -m json.tool`
2. `python3 -m newsroom.cli newsroom`
3. `bash scripts/burnin-check.sh`
4. Clear stale ticks: startup reconciliation or manual reconcile (above)
5. OpenAI quota: billing dashboard OR enable fallback env for burn-in

## Sign-off

| Role | Date | Notes |
|------|------|-------|
| Operator | | |
| Engineering | | |

**Verdict:** ☐ READY for controlled public  ☐ CONDITIONAL  ☐ NOT READY
