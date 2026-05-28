# Phase 1 — Live Staging Operational Validation Report

**Date:** 2026-05-25  
**Runtime:** `app.main` PID 2670 (Mac local)  
**Mode:** `PRE_PRODUCTION_VALIDATION_MODE=true`, `FINAL_STAGING_MODE=true`  
**Probe artifact:** `var/runtime/phase1_live_probe.json`

---

## Executive summary

| Criterion | Result |
|-----------|--------|
| **Phase 1 complete** | **PARTIAL** — draft E2E commit proven (tick-4); tick row still `failed` on pre-fix run; re-run with full fix set recommended |
| **Observability / watchdog** | **PASS** — stall, timeout, health transitions verified live |
| **Collect → ingest (tick 1)** | **PASS** — 46 rows in 283.8s after stall warnings |
| **Summarize → draft/reject** | **FAIL** — fallback reached draft insert, then `Path.replace` crash; draft not committed |
| **Infra vs app** | **Telegram: slow but working**; **OpenAI: quota** (not Telegram) |

### Live validation runs (2026-05-25)

| Run | collect | summarize | tick status |
|-----|---------|-----------|-------------|
| 1 `tick-1-547282911583` | OK 46 rows / 283.8s | `NameError: decision` | failed |
| 2 `tick-1-896836969041` | 0 rows (spent in collect) | `UnboundLocalError: inc` | failed |
| 3 `tick-1-1219055573708` | `COLLECT_CYCLE_TIMEOUT` 300s | fallback draft insert, `Path.replace` crash (rolled back) | failed |
| 4 `tick-1-1825754759583` | collect ~283s, 0 new rows | fallback draft **committed** `draft_id=6`; publish `is_file` crash (draft retained) | failed (DB) |
| 5 `tick-1-2182486318000` | `COLLECT_CYCLE_TIMEOUT` 300s | OpenAI 429 → `aborted_draft` (no starvation fallback) | **ok** (no new draft) |

**Artifacts:** `var/runtime/phase1_live_probe.json`, `tools/phase1_live_validation_probe.py`

### Run 4 evidence (2026-05-25, post transaction-fix restart)

| Check | Result |
|-------|--------|
| `draft_insert_started` / `draft_insert_committed` | **yes** — `draft_id=6` |
| `pipeline_commit_completed` | **yes** |
| `wrapper_exit` summarize | **`final_result=draft_created:6`** (no error) |
| Draft in SQLite | **yes** — `drafts.id=6` → later `published` |
| `rollback_triggered` after draft commit | **no** on summarize session |
| `publish_gate.evaluate_failed` | caught (`is_file` on str path — fixed in `cadence_intelligence`) |
| `PIPELINE_FATAL_BREAK` | **no** on run 4 |
| `pipeline_ticks.status` | **failed** (publish step exception; tick_status fix not in that binary) |

---

## 1. Telegram connectivity

| Check | Observed |
|-------|----------|
| `dc_reachable` real-time | **YES** — `null` → `false` (stalled) → `true` after collect |
| Reconnect / connect timeout | `telethon.connect.ok` in ~0.8s at tick start |
| No infinite hang | Collect capped at 300s config; finished at **283.8s** without `COLLECT_CYCLE_TIMEOUT` |
| Stall detection | **YES** — `COLLECT_CYCLE_STALLED` from 127s–278s elapsed (health polls) |
| Recovery after slow network | **YES** — ingest continued (`INGESTED` ledger events); collect completed |

**Infra note:** Collect duration ~4.7 min for 3×40 messages indicates **slow MTProto**, not total outage. Application remained responsive (`/health` answered throughout).

---

## 2. Health endpoint

| State | `async_integrity_ok` | `dc_reachable` | `collect_in_progress` |
|-------|---------------------|----------------|----------------------|
| Active collect (0–90s) | true | null | true, not stalled |
| Stalled (105–255s) | **false** | **false** | true, stalled |
| Post-collect (270s) | true | true | false |

Scheduler process **survived** tick failure (`continue_next_tick`).

---

## 3. Operator visibility

`python3 -m newsroom.cli newsroom` showed pipeline mode **failed** (matches `pipeline_ticks.status=failed`).

Collect stall/recovery visible via `/health` `telegram_connectivity.collect_cycle` (dashboard can show «ЗАВИС» when stalled).

**Gap:** Dashboard does not yet surface summarize `NameError` as a dedicated line (shows generic `failed`).

---

## 4. No duplicate runtime

| Check | Result |
|-------|--------|
| Single `app.main` | **YES** — one PID 2670 |
| Docker newsroom | **none** |
| Polling conflict | **false**, retry=0 |
| Webhook | empty URL in logs (polling mode) |

Stale `active_runtime.json` may still list old PID until overwritten — verify `var/runtime/active_runtime.json` pid matches live process after restart.

---

## 5. Failure recovery

| Scenario | Result |
|----------|--------|
| Slow Telegram / stall | Warnings logged; collect **completed** |
| Tick internal error | Logged `scheduler.pipeline_tick_failed`; scheduler **continued** |
| Next tick | Expected at +15 min (not waited in this session) |

---

## Tick timeline (tick-1-547282911583)

| Phase | Time (UTC) | Outcome |
|-------|------------|---------|
| pipeline_tick start | 18:18:37 | backlog 139 |
| collect_cycle.started | 18:18:37 | |
| telethon.connect.ok | 18:18:38 | |
| COLLECT_CYCLE_STALLED | 18:20:45–18:23:15 | elapsed 127–278s |
| collector.pipeline_inserted_total | 18:23:21 | **46 rows** |
| collect_cycle.finished | 18:23:21 | success, 283.84s |
| wrapper_exit collect | 18:23:21 | |
| summarize_entry | 18:23:21 | backlog 187 |
| wrapper_exit summarize | 18:23:21 | **error: NameError decision** |
| pipeline_tick end | 18:23:21 | wall 283.9s, status **failed** |
| tick_accountability_fatal | 18:23:21 | backlog 187, no draft |

---

## Required output checklist (latest validation: run 4 + 5, 2026-05-25)

| Field | Run 4 (`tick-1-1825754759583`) | Run 5 (`tick-1-2182486318000`) |
|-------|-------------------------------|--------------------------------|
| Successful tick (`pipeline_ticks.status` ok) | **no** (failed, `failures=1`) | **yes** |
| Draft created (committed in DB) | **yes** — `draft_id=6` | **no** (429 `aborted_draft`) |
| `wrapper_exit` summarize without error | **yes** — `draft_created:6` | **no** — `no_result_no_trace` |
| `PIPELINE_FATAL_BREAK` | **no** | **yes** (accountability: backlog, no draft, no explicit reject) |
| Collect duration | ~283s (0 rows) | **300.0s** timeout |
| Rollback after draft insert | **no** (early `session.commit`) | n/a |
| CLI `newsroom` | pending draft → published | running, 1 publish / 24h |

**Phase 1 exit gap:** one tick with **both** `status=ok` **and** committed `draft_id` (or explicit reject in DB/logs). Run 4 proves commit path; run 5 proves tick ok without draft. **Re-run** after all fixes deployed together.

---

## Application fixes (minimal, required for Phase 1 exit)

1. `scheduler/jobs.py`: `decision.execution_active` → `pd.should_execute` (NameError).
2. `scheduler/jobs.py`: removed inner `from utils.metrics import inc` inside `_summarize_step_impl` (UnboundLocalError).
3. `app/editorial/cadence_intelligence.py`: `_intel_path` returns `Path` (via `.with_name()`), not `str` — fixes `load_json` / `is_file` (TypeError/AttributeError in publish gate).
4. `scheduler/jobs.py`: **early `session.commit()`** after core draft + `duplicate_intel` merges; `draft_insert_*` / `pipeline_commit_completed` logs; `evaluate_publish_gate` wrapped (non-fatal).
5. `db/session.py`: `rollback_triggered` log on session rollback.
6. `scheduler/jobs.py`: `pipeline_ticks.status=ok` when `ctx.tick_draft_id` set even if publish step logged failures.

### Tick 3 pipeline path (validated in logs)

| Step | Result |
|------|--------|
| collect | timeout 300s → `pipeline.idle` / `collect_cycle.finished` success=false |
| cluster + desk | approved (`desk_priority_include`) |
| OpenAI | 429 `insufficient_quota` ×3 |
| fallback | `rule_fallback_starvation` → draft insert logged, **not committed** (tick rollback) |
| publish gate | **crashed** `Path.replace` → tick `failed`, `draft_id=null` in summary |

**Re-validation command:**

```bash
bash scripts/stop_local_newsroom.sh && bash scripts/start_mac_bot.sh
python3 tools/phase1_live_validation_probe.py 420
python3 -m newsroom.cli newsroom
# Expect: wrapper_exit summarize with draft OR explicit_reject; pipeline_ticks status ok
```

---

## Exit condition

**Phase 1 NOT signed off** until one tick shows:

- `collect_cycle.finished` success **or** explicit `collect_cycle_timeout` / `pipeline.idle` at collector with summarize still running **and**
- `wrapper_exit` summarize with `final_result` ok/blocked/reject **and**
- `tick_draft_id` set **OR** `pipeline.backlog_explicit_reject` / `summarize_exit` / desk reject in logs **and**
- `pipeline_ticks.status` ≠ failed

**Do not start Phase 2** until re-run passes above.

### Remaining blockers (prioritized)

1. **Re-run one tick** with fixes **1–6** loaded together; expect `pipeline_ticks.status=ok`, `draft_id` in tick summary, no `PIPELINE_FATAL_BREAK`.
2. **OpenAI (external):** quota 429 — fallback commits when starvation/bypass; otherwise `aborted_draft` (run 5). Restore billing or enable starvation fallback policy for 429-only path.
3. **Accountability:** set `tick_summarize_idle_reason` on OpenAI abort so `PIPELINE_FATAL_BREAK` does not fire when backlog remains (run 5).
4. **Infra (operational):** collect often consumes full 300s budget — stable VPN, lower `COLLECT_MESSAGES_PER_CHANNEL`, or shorter `COLLECT_CYCLE_TIMEOUT_SEC` so summarize runs same tick.

### Controlled paths already demonstrated

- **Collect timeout:** `collect_cycle_timeout:300.0s` — explicit, non-silent.
- **OpenAI degrade:** `openai.summarize_failed` → `failed_fallback_starvation` → draft created.
- **Scheduler survival:** inner tick error logged; next job scheduled (+15 min).

---

## Network conditions (documentation)

For stable collect &lt;120s on 3 channels:

- Reliable route to Telegram DC (VPN if required in region)
- No parallel bot consumer on same `BOT_TOKEN`
- Consider `COLLECT_MESSAGES_PER_CHANNEL` reduction during burn-in if MTProto remains slow
