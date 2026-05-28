# Burn-in validation (read-only)

Operational proof that the pipeline state machine is stable over time. **No runtime or pipeline code changes** — only DB + log observation.

## Quick start

```bash
bash scripts/burnin-check.sh
```

Exit codes: `0` = PASS, `2` = CONDITIONAL, `1` = FAIL.

Post-restart / post-deploy window (ignore legacy ticks without `terminal_state`):

```bash
export BURNIN_SINCE_TICK_ID=30   # first tick id after resolver deploy
bash scripts/burnin-check.sh
```

## Tools

| Command | Purpose |
|---------|---------|
| `python3 tools/burnin_validation.py snapshot` | Finished vs active ticks, metrics, log contract |
| `python3 tools/burnin_validation.py check` | PASS / CONDITIONAL / FAIL |
| `python3 tools/burnin_validation.py sql finished` | Print finished-tick SQL |
| `python3 tools/burnin_validation.py sql active` | Print in-flight SQL |

Artifacts: `var/runtime/burnin_snapshot.json` (from `burnin-check.sh`).

SQL file: `docs/sql/burnin_finished_ticks.sql`

## What counts for burn-in

### Included (metrics + readiness)

- Rows with `finished_at IS NOT NULL`
- Tail **consecutive** finished ticks from highest `id` downward until the first in-flight row
- Each must have `status` ∈ `{ok, reject}`
- Each must have `detail_json.terminal_state` ∈ `{committed_draft, committed_reject, committed_idle}`

### Excluded (shown separately, not in rates)

- `status = running` or `finished_at IS NULL`
- Stuck active ticks (`age_sec` > 1h) → CONDITIONAL warning, not FAIL

### Log contract (tail scan, default 8MB)

| Signal | Meaning |
|--------|---------|
| `aborted_draft` | **FAIL** if > 0 (pre-resolver behavior) |
| `PIPELINE_FATAL_BREAK` | **FAIL** if > 0 |
| `pipeline.terminal_state` | Resolver firing |
| `summarize_exit` reject | Explicit terminal reject path |
| `openai_429` / `openai.summarize_failed` | Quota pressure (informational) |
| `rule_fallback` | Fallback path usage |

## Verdicts

| Verdict | Meaning |
|---------|---------|
| **PASS** | ≥3 consecutive finished tail ticks; all valid; log contract clean |
| **CONDITIONAL** | Correctness likely OK but sample too small, log unavailable, in-flight gap, or stuck active ticks |
| **FAIL** | Invalid status, missing `terminal_state`, `aborted_draft`, or `PIPELINE_FATAL_BREAK` |

## Controlled public GO checklist

All required:

1. **3–7** consecutive finished ticks in tail (no in-flight gap at head)
2. Every finished tick in that window: `terminal_state` present, `status` ok|reject
3. Log: zero `aborted_draft`, zero `PIPELINE_FATAL_BREAK` in burn-in window
4. **Golden tick** (optional strict gate): one tick with `status=ok`, `terminal_state=committed_draft`, `draft_id` set — use `check --require-golden`
5. Preview/publish parity spot-check per publish (manual)
6. 3–7 day daily log in `docs/BURN_IN_OPERATIONS.md`

## Interpreting snapshot sections

```
=== BURN-IN SNAPSHOT ===
Verdict / tail consecutive count
Finished window metrics     ← only finished rows (reject_rate, terminal breakdown)
Resolver-era metrics        ← finished rows that have terminal_state (post-resolver)
Log contract + signals
ACTIVE / IN-FLIGHT          ← excluded from rates
FINISHED TICKS table
TAIL STREAK                 ← what readiness checker evaluates
```

**High reject rate** during burn-in is normal under source cooldown, desk reject, or OpenAI 429 — it proves deterministic `committed_reject`, not silent failure.

## Makefile

```bash
make burnin-check
make burnin-snapshot
```

## Output recovery (starvation)

If channel is silent but ticks show `committed_reject` / `source_cooldown`:

```bash
export BURNIN_SOFT_GOVERNANCE=true
export BURNIN_OPENAI_ALWAYS_FALLBACK=true
bash scripts/stop_local_newsroom.sh && bash scripts/start_mac_bot.sh
```

Stale `running` rows (blocks metrics):

```bash
python3 -c "import asyncio; from app.config import load_settings; from app.reliability.stale_tick_recovery import reconcile_stale_pipeline_ticks; print(asyncio.run(reconcile_stale_pipeline_ticks(load_settings(), source='manual')))"
```

Golden tick + publish path:

```bash
make golden-check
```

## Related

- Daily ops: `docs/BURN_IN_OPERATIONS.md`
- Pre-public sign-off: `docs/PREPUBLIC_CHECKLIST.md`
- Pre-launch status: `docs/FINAL_PRE_LAUNCH_REPORT.md`
