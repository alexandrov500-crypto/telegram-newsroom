# P1.5 Editorial & Publish Throughput Investigation Report

**Date:** 2026-05-30  
**Environment:** VPS production (`213.171.3.133`), DB `/data/newsroom.db`  
**Context:** Post-P0/P0.5/P1.0 — collect cycle ~3s, timeout eliminated, ingest restored  
**Audit tool:** `tools/p15_editorial_publish_audit.py`

---

## Executive Summary

**Collector is no longer the primary bottleneck.** Collect cycle dropped from ~166s to **~3s**; pipeline wall time is now dominated by summarize + editorial + publish (~5–170s/tick post-fix, mostly publish/cadence).

**24-hour historical bottleneck: A — Editorial rejection** (61% of drafts rejected; `publication_risk:0.30` + OpenAI fallback failures).

**Current bottleneck (post editorial/publish hotfix, post-P1.0): C — Cadence throttling** — approved drafts **#135, #136** blocked by `growth_cadence_session_cap` and `publish_gate_min_interval` despite passing editorial.

**Secondary limiter: E — Low effective input flow** — only **36 raw posts / 24h** (collector broken most of day); **135 raw posts still unprocessed** in backlog.

---

## 1. Pipeline Funnel (24h)

| Stage | Count | Conversion (from prior stage) | Conversion (from raw) |
|-------|------:|------------------------------:|----------------------:|
| **Raw Posts** (collected) | 36 | 100% | 100% |
| Raw Posts (processed) | 73 | 203%* | 203%* |
| **Drafts Created** | 57 | 78% of processed raw | 158%* |
| Drafts Rejected | 35 | **61.4%** | 97% |
| Drafts Failed | 9 | 15.8% | 25% |
| **Drafts Published** | 11 | **19.3%** | **30.6%** |
| Approved (backlog now) | 2 | — | — |
| Queued (scheduled_publish_at set) | 12 | — | — |
| Publish attempted (publish_attempts > 0) | 18 | 31.6% | 50% |

\* >100% because summarizer consumed **backlog raw** (135 still unprocessed) in addition to same-day ingest.

### Maximum material loss point

```
Raw (36) → Draft (57) → ✂️ REJECTED (35) → Published (11)
                              ↑
                    61% of drafts die here
```

**Editorial rejection** is the largest funnel collapse over 24h. Publish failures (9) are secondary.

---

## 2. Editorial Rejection Analysis

Sample: **last 100 rejected drafts** (40 within 24h window).

| Reason | Count | % |
|--------|------:|--:|
| `openai_error_rules_insufficient` | 13 | 32.5% |
| `manual:publication_risk:0.30` | 12 | 30.0% |
| `unknown` | 5 | 12.5% |
| `manual:publication_risk:0.43` | 2 | 5.0% |
| `manual:publication_risk:0.29` | 2 | 5.0% |
| `w3:forbidden_voice` | 2 | 5.0% |
| Other `publication_risk:*` | 4 | 10.0% |

**Publication_risk aggregate:** ~52.5% of sampled rejections (all `manual:publication_risk:*` variants).

### Answers

| Question | Finding |
|----------|---------|
| What most often causes reject? | **`publication_risk` gate (rules)** + **OpenAI unavailable / low-confidence fallback** |
| False positives? | **Yes** — risk scores 0.28–0.30 with `trust_score ~0.58`, `single_source` factor; content was news-grade (e.g. Ferrari, Russia party news later approved post-fix) |
| Is `publication_risk` too aggressive? | **Yes for autonomous mode** — threshold treats `mandatory_review` at ~0.29–0.30 as hard reject before AI stamp; pre-hotfix code ignored `review_cleared` bypass |

**Duplicate filtering:** 0 rejections with `duplicate_intel.max_similarity_pct > 50%` in 24h → **not a bottleneck**.

Typical rejected draft extras:

```json
{
  "ai_editorial_review": {
    "approved": false,
    "confidence": 0.45,
    "reason": "manual:publication_risk:0.30",
    "source": "rules"
  }
}
```

---

## 3. Approval Gate & Latency

Published drafts with `moderated_at` (24h): **n=11**

| Metric | create → moderated_at (approval) |
|--------|-------------------------------------|
| **p50** | **1.4s** |
| **p95** | 855s (outlier: draft waited in queue pre-fix) |
| **max** | 855s |

Post hotfix publishes (e.g. #133, #134):

| draft_id | created_at | moderated_at | Δ |
|----------|------------|--------------|---|
| 133 | 14:19:43 | 14:19:44 | **~1s** |
| 134 | 14:23:38 | 14:23:40 | **~2s** |
| 115 | 07:37:48 | 07:37:50 | **~2s** |

**Verdict:** Once editorial passes, **approval is immediate** (~1–2s). Approval gate is **not** the latency bottleneck post-fix.

---

## 4. Publish Scheduler Analysis

### Current container (post-P1.0, 3 pipeline ticks)

| Metric | Value |
|--------|------:|
| Publish cycles (pipeline ticks) | 3 |
| Publish succeeded | 2 |
| Publish failed | 0 |
| Skipped / deferred | 4 |

### Skip reason table (structured logs)

| Skip Reason | Count |
|-------------|------:|
| `cadence_deferred` (outcome) | 4 |
| `publish_gate_min_interval` | 2 |
| `growth_cadence_session_cap` | 2 |

Example blocked publish:

```
publish.cadence_blocked draft_id=135 reasons=[growth_cadence_session_cap, publish_gate_min_interval]
→ outcome=cadence_deferred
```

### Active cadence env

| Setting | Value |
|---------|-------|
| `PUBLISH_CHANNEL_MIN_INTERVAL_SEC` | 90 |
| `GROWTH_CADENCE_DAILY_CAP` | 20 |
| `GROWTH_CADENCE_ENGINE_ENABLED` | true |
| `PUBLISH_FLOOR_MAX_SILENCE_MIN` | 30 |
| `AUTO_PUBLISH_MAX_SCHEDULE_PER_TICK` | 4 |

**Paradox:** `DESK_STARVATION_AUTO_PUBLISH=true` and starvation detected in metrics, but **growth session cap still blocks** approved drafts #135/#136 every 10 min tick.

### 24h publish attempts

| | Count |
|---|------:|
| publish_attempts (sum) | 18 |
| published | 11 |
| failed | 9 |

Failure reasons (failed drafts): `premium_policy_low_signal`, `TelegramNetworkError timeout` — not cadence.

---

## 5. Throughput Before / After P1.0

| Window | raw/h | drafts/h | publishes/h |
|--------|------:|---------:|------------:|
| **Before P1.0** (24h ending 14:23 UTC) | 1.46 | 2.25 | **0.42** |
| **After P1.0** (~0.5h sample) | 2.00 | 6.00 | **2.00** |

| Metric | Before | After P1.0 + editorial hotfix |
|--------|--------|-------------------------------|
| Editorial reject rate | ~61% | **0%** (0/3 drafts in sample) |
| Collect cycle | 166s avg | **3s** |
| Publish outcome | `approve_denied` | **`cadence_deferred`** |

**Publish throughput improved ~4.8× in short window**, but hits **cadence ceiling** before reaching theoretical capacity.

**Theoretical capacity post-P1.0:**

| Stage | Limit |
|-------|-------|
| Collect | ~1200 cycles/h (3s each) — **not binding** |
| Pipeline tick | ~3 ticks/h (20 min interval) → max **~3 drafts/h** |
| Cadence min interval | 90s → max **~40 publishes/h** — not binding |
| Growth daily cap | **20/day** |
| **Effective cap** | **~1 publish / 10 min** when cadence session cap active |

---

## 6. Backlog Analysis

| Metric | Value |
|--------|------:|
| Unpublished approved drafts | **2** (#135, #136) |
| Oldest approved age | ~11 min (at audit) |
| Pending drafts | 0 |
| Unprocessed raw posts | **135** |
| Scheduled queue (24h) | 12 |

**Content accumulation before publish:** **Yes** — 2 approved drafts waiting on cadence; 135 raw posts waiting on summarizer. This is **downstream backlog**, not collector backlog.

---

## 7. Bottleneck Determination

| Option | Verdict | Evidence |
|--------|---------|----------|
| **A. Editorial rejection** | **Primary (24h historical)** | 35/57 drafts rejected (61%); publication_risk 52% |
| **B. Publish scheduler** | Secondary | 18 attempts → 11 success; scheduler runs but defers |
| **C. Cadence throttling** | **Primary (current state)** | 100% of recent publish skips = cadence; approved backlog |
| **D. Duplicate filtering** | **Rejected** | 0 duplicate-based rejections |
| **E. No bottleneck / low flow** | **Secondary** | 36 raw/24h; 135 unprocessed; pipeline tick ~20 min |

### Selected bottleneck

**E → A → C (time-series multi-factor)**

1. **During broken collector period:** low raw input (E)  
2. **After ingest restored, pre-hotfix:** editorial rejection (A)  
3. **After editorial/publish hotfix + P1.0:** cadence throttling (C)

Collector **confirmed not primary** — collect 3s vs tick wall 5–7s post-fix; pipeline tick interval and downstream gates set throughput ceiling.

---

## 8. Recommended P2 Fixes

| Priority | Fix | Rationale |
|----------|-----|-----------|
| **P2.0** | Commit editorial + publish hotfixes to `main` | Prevent regression on redeploy |
| **P2.1** | Cadence starvation bypass: when `publish_starvation_detected` or approved backlog > 0 for >10 min, skip `growth_cadence_session_cap` | Unblocks #135/#136 class |
| **P2.2** | Autonomous mode: treat `publication_risk < 0.35` as pass with AI rules stamp (not hard reject) | Fixes 52% rejection cluster |
| **P2.3** | Fix `openai_error_rules_insufficient` — rules fallback must approve when `AUTONOMOUS_EDITORIAL_MODE=true` | 32.5% reject bucket |
| **P2.4** | Increase summarize throughput for 135 raw backlog (parallel cluster or higher per-tick limit) | Raises draft input to publish path |
| **P2.5** | Observability: log `publish.cadence_blocked.reasons` to metrics counter by reason | Enables P2 cadence tuning |
| **P2.6** | Review `GROWTH_CADENCE_DAILY_CAP=20` vs actual 11/day — cap not binding yet; **session cap is** | Target session cap logic |

---

## Final Answer

> **If collector now runs in ~3 seconds, why does the system still publish fewer materials than it could theoretically process?**

Because **throughput is no longer collector-limited** — it is limited by:

1. **Pipeline tick rate** (~1 draft created every 20 minutes)  
2. **Historical editorial rejection** (61% of drafts never reached publish — fixed by hotfix but not in git)  
3. **Growth cadence gates** (`growth_cadence_session_cap`, `publish_gate_min_interval`) deferring **already-approved** drafts  
4. **Low net ingest** over 24h (36 raw) due to collector outage earlier in the window, plus **135 raw backlog** not yet summarized  

The system **can process** much faster than it **publishes** because the binding constraints moved to **editorial policy (24h)** and **publish cadence policy (now)** — not Telethon collect time.

**Proof:** Post-P1.0 tick wall time **~5–7s** (collect 3s + summarize + publish attempt) vs **20 min** tick interval; approved drafts exist but `cadence_deferred` prevents send.

---

*Generated: P1.5 investigation. Data sources: SQLite `/data/newsroom.db`, docker logs `telegram-newsroom` (current container + 24h DB history).*
