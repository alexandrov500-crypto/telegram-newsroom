# Burn-in operations — controlled staging (3–7 days)

**Status:** CONDITIONAL GO — staging exposure only.  
**Not:** full public scale.

**Burn-in interpretation:** see [`docs/BURN_IN_VALIDATION.md`](BURN_IN_VALIDATION.md).

---

## Daily operator checklist (15 min)

1. `python3 -m newsroom.cli newsroom` — pipeline mode, backlog, last publish.
2. `curl -s http://127.0.0.1:8080/health | python3 -m json.tool` — `status`, `async_integrity_ok`, `telegram_connectivity`.
3. **Burn-in snapshot + readiness** (finished ticks only; in-flight excluded from rates):

```bash
bash scripts/burnin-check.sh
# or separately:
python3 tools/burnin_validation.py snapshot --log logs/local-run.log
python3 tools/burnin_validation.py check --log logs/local-run.log --min-ticks 3
```

Exit codes for `check`: `0` = PASS, `2` = CONDITIONAL, `1` = FAIL.

**Interpretation:**

| Verdict | Meaning |
|---------|---------|
| PASS | ≥3 consecutive **finished** ticks from highest `id` (no in-flight gap), each `status` ∈ {ok, reject}, each has `terminal_state`, log has no `aborted_draft` / `PIPELINE_FATAL_BREAK` |
| CONDITIONAL | Correctness likely OK but sample too small, log unavailable, or in-flight ticks blocking tail streak |
| FAIL | Invalid status, missing `terminal_state`, or contract violations in logs |

Raw SQL (finished only): `docs/sql/burnin_finished_ticks.sql`

4. Legacy quick tick peek:

```bash
sqlite3 data/newsroom.db \
  "SELECT id,status,drafts_created,finished_at,substr(detail_json,1,100) FROM pipeline_ticks ORDER BY id DESC LIMIT 5;"
```

5. Log grep:

```bash
grep -cE "PIPELINE_FATAL_BREAK|public_content_leak|PUBLIC_CONTENT_LEAK|publish_quality_gate" logs/local-run.log | tail -5
grep -c "COLLECT_CYCLE_TIMEOUT" logs/local-run.log
grep -c "draft_insert_committed" logs/local-run.log
```

6. For each publish: `/preview_channel <id>` → approve → spot-check channel (no JSON, no CTA, matches preview).

JSON artifact (optional): `var/runtime/burnin_snapshot.json` from `burnin-check.sh`.

---

## Daily log (copy row per day)

| Day | Ticks ok | Ticks failed | Publishes | Sanitizer block | Lock violation | QG warnings | Collect timeouts | Notes |
|-----|----------|--------------|-----------|-----------------|----------------|-------------|------------------|-------|
| D0 | 1 (#34) | many reject | 1 (#6) | 0 | 0 | | | Golden tick #34 draft_id=7 (fallback); stale 4 ticks reconciled |
| D1 | | | | | | | | |
| D2 | | | | | | | | |
| D3 | | | | | | | | |
| D4 | | | | | | | | |
| D5 | | | | | | | | |
| D6 | | | | | | | | |
| D7 | | | | | | | | |

**Limits:** `FINAL_STAGING_MAX_PUBLISHES_PER_HOUR <= 6`. Manual approval required.

---

## Strict golden tick (one-time gate)

**Pass:** `pipeline_ticks.status = ok` **and** (`detail_json` contains `draft_id` **or** explicit reject in `summarize_idle` / trace).

**Fail:** any `aborted_draft` in logs (post-resolver builds should be zero). Historical lines before deploy are ignored if you scan only recent log tail via `burnin_validation.py`.

**Paths to pass under quota:**

| Path | Action |
|------|--------|
| A | Restore OpenAI billing |
| B | Wait for desk starvation recovery (`starvation_recovery_active: true` in metrics) → `rule_fallback_starvation` |
| C | Staging-only: documented minimal/bypass modes (ops policy, not default) |

**Validation run:**

```bash
bash scripts/stop_local_newsroom.sh && bash scripts/start_mac_bot.sh
python3 tools/phase1_live_validation_probe.py 420
```

Verify after tick:

```bash
sqlite3 data/newsroom.db "SELECT id,status,detail_json FROM pipeline_ticks ORDER BY id DESC LIMIT 1;"
grep -E "draft_insert_committed|summarize_exit|pipeline.tick.summary|rule_fallback" logs/local-run.log | tail -15
```

---

## Quality gate policy

| Setting | Value |
|---------|--------|
| `PUBLISH_QUALITY_GATE_STRICT` | **false** until golden tick + 5 clean publishes |
| Strict scope (when enabled) | metadata / JSON / debug only |
| Never block | readability, tone, style |

---

## Transition to FULL CONTROLLED PUBLIC GO

All required:

- [ ] Strict golden tick recorded
- [ ] 3–7 day burn-in table complete
- [ ] Zero sanitizer/lock violations in burn-in window
- [ ] Quota stable 48h OR fallback-only policy signed
- [ ] `FINAL_STAGING_CHECKLIST` signed
- [ ] Optional: `PUBLISH_QUALITY_GATE_STRICT=true`

---

## Rollback (no deploy)

```bash
bash scripts/stop_local_newsroom.sh
# unset EDITORIAL_TUNING_PATH; PUBLISH_QUALITY_GATE_STRICT=false
# emergency_halt via ops control plane if needed
```
