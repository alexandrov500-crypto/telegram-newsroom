# Final pre-launch report — controlled public access readiness

**Date:** 2026-05-25  
**Verdict:** **CONDITIONAL GO** (limited public exposure under staging controls)  
**Not:** full unconditional public launch

---

## 1. Operational readiness

| Layer | Status | Evidence |
|-------|--------|----------|
| Runtime / scheduler | **Ready** | Process healthy; ticks complete; no event-loop death on failures |
| Collect watchdog | **Ready** | `COLLECT_CYCLE_STALLED`, `COLLECT_CYCLE_TIMEOUT`, clean disconnect |
| Telegram connectivity | **Degraded but managed** | Slow MTProto (~300s); timeout + recovery; not infinite hang |
| Draft commit path | **Ready** | Early commit; `draft_insert_committed`; draft survives gate errors |
| Publish path | **Proven** | Draft **#6** `published`; `public_output_lock` ok (516 chars HTML) |
| Editorial hardening | **Integrated** | Scrubber, tuning YAML, `/preview_channel`, quality gate log-only |
| Import safety | **Fixed** | `test_final_staging_release` + `test_staging_mode` collect |
| Test bundles | **Passing** | 35 tests (editorial + staging) |

**Live runtime (snapshot):** PID `app.main`, `/health` → `healthy`, `async_integrity_ok=true`, `dc_reachable=true`.

---

## 2. Golden tick status (Phase A)

**Strict definition:** one tick with `pipeline_ticks.status=ok` **and** `draft_id` committed **in that same tick** (or explicit terminal reject recorded in tick detail).

| Run | Tick | `pipeline_ticks` | Draft in tick | Outcome |
|-----|------|------------------|---------------|---------|
| Best commit | (run 4, prior session) | `failed` | draft **#6** committed | `wrapper_exit` `draft_created:6`; publish later |
| Latest ok | `tick-1-2182486318000` (id **26**) | **ok** | `draft_id=null` | OpenAI 429 → `aborted_draft`; publish gate blocked draft 5 |
| Failed | id **25** | `failed` | `drafts_created=1` | Likely draft 6; tick marked failed |

**Published E2E (operational):** Draft **#6** — `published` at 2026-05-25 18:44:59 UTC; publish HTML passed output lock (`violations: []`). This is the **first successful real published outcome** (collect → summarize → editorial → publish), even though the strict single-tick DB row is not clean.

**Golden tick:** **NOT formally signed** — re-run required after OpenAI billing restore **or** confirmed `rule_fallback_starvation` on quota ticks.

**Why 429 → `aborted_draft` (tick 26):** Fallback on OpenAI failure runs only when `publish_starvation_detected` **or** minimal/bypass mode (`scheduler/jobs.py`). Tick 26 had `starvation_recovery_active: false` → explicit suppress, not fatal crash. For golden tick under quota without billing: wait for starvation recovery **or** restore quota **or** use documented bypass only in staging (not a code change).

### Phase A procedure (operator)

```bash
bash scripts/stop_local_newsroom.sh && bash scripts/start_mac_bot.sh
curl -s http://127.0.0.1:8080/health | python3 -m json.tool
python3 tools/phase1_live_validation_probe.py 420
```

**Capture per tick:**

| Field | Source |
|-------|--------|
| collect duration | `pipeline.timings` / `collect_cycle.finished` |
| summarize duration | `openai_sec` in timings |
| retries | `openai_retries`, `telethon_reconnects` |
| fallback | `openai.summarize_failed` → `failed_fallback_starvation` or `aborted_draft` |
| final status | `pipeline_ticks.status`, `pipeline.tick.summary` |
| committed id | `drafts.id`, `summarize_exit` / `draft_insert_committed` |

**Pass line:** `status=ok` AND (`detail_json.draft_id` set OR explicit `summarize_idle` reject reason) AND no post-commit rollback.

---

## 3. Remaining risks

| Risk | Severity | Mitigation |
|------|----------|------------|
| Collect consumes full 300s tick | **High (ops)** | VPN; lower `COLLECT_MESSAGES_PER_CHANNEL`; shorter `COLLECT_CYCLE_TIMEOUT_SEC` for burn-in |
| OpenAI `aborted_draft` on 429 | **High (external)** | Billing; verify starvation fallback triggers (not only `aborted_draft`) |
| `PIPELINE_FATAL_BREAK` with backlog | **Medium** | Accountability noise; tick may still be `ok`; improve `summarize_idle` on abort |
| Stale `pipeline_ticks` `running` (ids 20–21) | **Low** | DB hygiene; does not block runtime |
| Task watchdog warnings (polling >600s) | **Low** | Long-lived tasks; informational unless tasks die |

---

## 4. External dependency risks

| Dependency | Assessment |
|------------|------------|
| **OpenAI API** | `insufficient_quota` observed; 3 retries/tick; publish **not** blocked by quota (draft 6 published via fallback path earlier) |
| **Telegram MTProto** | Slow but not fatal; stall visibility works |
| **Operator availability** | Manual approval + `/preview_channel` required for controlled launch |

**Quota stability:** Treat as **unstable** until 48h without `aborted_draft` on backlog ticks **or** billing restored.

---

## 5. Rollback plan

| Action | Command / config |
|--------|------------------|
| Stop runtime | `bash scripts/stop_local_newsroom.sh` |
| Disable strict leak block | `PUBLISH_QUALITY_GATE_STRICT=false` (default) |
| Disable sanitizer block | `PUBLIC_CONTENT_SANITIZER_STRICT=false` |
| Revert editorial tuning | unset `EDITORIAL_TUNING_PATH` |
| Emergency halt | ops control plane `emergency_halt` / env per runbook |
| Import fix rollback | revert `app/recovery/__init__.py` + lazy imports in `pipeline_state_engine.py` |

No DB migrations in this stabilization phase.

---

## 6. Burn-in evidence (Phase B)

**Status:** **Not started / insufficient** for multi-day sign-off.

**Minimum burn-in:** 3–7 days, `FINAL_STAGING_MODE=true`, `FINAL_STAGING_MAX_PUBLISHES_PER_HOUR<=6`.

### Daily monitoring (template)

| Day | Ticks ok/failed | Publishes | Sanitizer blocks | Output lock violations | QG warnings | Notes |
|-----|-----------------|-----------|------------------|------------------------|-------------|-------|
| D0 | 1/4+ | 1 (draft 6) | 0 | 0 | TBD | Baseline |
| D1–D7 | | | | | | |

### Log grep (daily)

```bash
grep -cE "PIPELINE_FATAL_BREAK|public_content_leak|PUBLIC_CONTENT_LEAK|publish_quality_gate.*block" logs/local-run.log
grep -c "COLLECT_CYCLE_TIMEOUT" logs/local-run.log
grep -c "draft_insert_committed" logs/local-run.log
python3 -m newsroom.cli newsroom
```

Watch: scheduler drift, memory, duplicate publishes (`ledger_dropped_duplicates`), `emergency_halt`.

---

## 7. Quality gate transition (Phase C)

| Setting | Current | After burn-in |
|---------|---------|---------------|
| `quality_gate.mode` (YAML) | `log_only` | keep `log_only` until 5 clean publishes |
| `PUBLISH_QUALITY_GATE_STRICT` | **false** (assumed) | `true` — **metadata/debug leaks only** |
| Blocks readability / tone | **No** | **No** (by design) |

**Strict leak blocking:** **Not enabled** — enable only after burn-in with zero sanitizer/lock violations in logs.

---

## 8. Controlled public access (Phase D)

| Control | Recommendation |
|---------|----------------|
| Publish rate | `FINAL_STAGING_MAX_PUBLISHES_PER_HOUR=6` (or lower) |
| Approval | **Manual** — preserve admin approve flow |
| Preview | **Mandatory** `/preview_channel <id>` before approve |
| Emergency halt | Verified available (`emergency_halt: false` in metrics) |
| Autoscaling | **None** |
| Editorial supervision | Human review for gate blocks (`publication_risk`, manual_review) |

**Recommended rollout size:** Single channel, ≤6 posts/hour, 1 operator on-call, 7-day staging window before raising caps.

---

## 9. Operator monitoring cadence

| Interval | Action |
|----------|--------|
| Each publish | `/preview_channel` → approve → spot-check channel post |
| Every pipeline tick (15 min) | `python3 -m newsroom.cli newsroom` or dashboard |
| Daily | Burn-in table + log grep + `pipeline_ticks` last 10 rows |
| On alert | `PIPELINE_FATAL_BREAK`, sanitizer block, collect timeout streak |

---

## 10. GO / CONDITIONAL GO / NO GO

### CONDITIONAL GO — controlled public access (staging channel)

**Granted when all are true:**

- [x] Runtime survives failures; publish path works
- [x] Preview/publish parity (`build_channel_message_html`)
- [x] Editorial hardening + no output lock violations on draft 6 publish
- [x] Import/tests pass (35)
- [x] First real published post (draft #6)
- [ ] **Formal golden tick** (ok + same-tick draft_id)
- [ ] **3–7 day burn-in** with daily summaries
- [ ] OpenAI quota stable or fallback-only policy signed off

### NO GO — full public launch

Until: golden tick, burn-in complete, `PUBLIC_LAUNCH_CHECKLIST` / `FINAL_STAGING_CHECKLIST` signed, optional `PUBLISH_QUALITY_GATE_STRICT=true`.

---

## Appendix — import cycle fix

```
final_publish_gate → minimal_newsroom → app.recovery.pipeline_overrides
  → app.recovery.__init__ (slim: overrides only)
app.state.pipeline_decision_engine → app.state.__init__ → pipeline_state_engine
  → lazy import build_pipeline_decision_context
```

Tests: `pytest tests/test_final_staging_release.py tests/test_staging_mode.py -q` → 13 passed.

---

## Appendix — editorial config defaults

See `config/editorial_tuning.yaml`: `include_cta: false`, `attribution.style: source`, `quality_gate.mode: log_only`.

Commands:

```bash
python3 -m pytest tests/test_publish_body_scrubber.py tests/test_publish_quality_gate.py \
  tests/test_public_post_formatter.py tests/test_public_content_sanitizer.py \
  tests/test_publish_formatting.py tests/test_editorial_tuning_loader.py \
  tests/test_final_staging_release.py tests/test_staging_mode.py -q
```
