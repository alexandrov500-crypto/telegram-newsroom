# 72h operational findings

Living log for the stabilization window after v3.1 production-lite activation. **Observation only** — no feature churn ([stabilization_freeze_policy.md](../governance/stabilization_freeze_policy.md)).

## Window metadata

| Field | Value |
|-------|-------|
| Start (UTC) | _YYYY-MM-DD HH:MM_ |
| End (UTC) | _+72h_ |
| Tag deployed | `v3.1-production-lite` |
| Operator owner | _name_ |
| Tier | T1 single-worker |
| Publish cap | ≤5/day (week 1) |

## Review cadence (required)

| Cadence | Action | Owner |
|---------|--------|-------|
| Every 4h | `make live-telegram-diagnostics` → archive JSON | Operator |
| Immediate | Any MEDIUM+ incident → [incident_response.md](../runbooks/incident_response.md) | Operator |
| Daily | Summary section below (24h block) | Operator |

---

## Metric baselines (fill per snapshot)

Capture from `make live-telegram-diagnostics` → `operational` block. First row = H0 baseline; subsequent rows every 4h.

| Time (UTC) | `publish_retries` | `telethon_reconnects` | `telethon_flood_waits` | `publish_failures` | `publish_lock_contention` | `session_reset_suspected` | Notes |
|------------|-------------------|----------------------|------------------------|--------------------|---------------------------|---------------------------|-------|
| H0 | | | | | | | |
| H+4 | | | | | | | |
| H+8 | | | | | | | |
| … | | | | | | | |
| H+72 | | | | | | | |

**Derived baselines (72h aggregate)** — transfer to [production_baselines.md](production_baselines.md):

| Metric | 72h min | 72h max | 72h typical | vs healthy range |
|--------|---------|---------|-------------|------------------|
| Retry amplification (`publish_retries` delta) | | | | |
| Reconnect frequency | | | | |
| FloodWait count | | | | |
| Publish failures | | | | |
| Lock contention events | | | | |

---

## Publish latency & throughput

From structured logs: `publish.telegram_chunks_duration_sec`, `publish.db_finalize_duration_sec`.

| Day | Publishes (count) | Avg chunk duration (s) | Max chunk duration (s) | Cadence blocks | Operator notes |
|-----|-------------------|------------------------|------------------------|----------------|----------------|
| 1 | | | | | |
| 2 | | | | | |
| 3 | | | | | |

**Moderation throughput (qualitative):**

| Metric | Observation |
|--------|-------------|
| Avg time approve → publish | |
| Reject rate | |
| Operator interventions / day | |
| Fatigue signals | |

---

## Anomalies

| ID | Time | Signal | Severity | Action taken | Resolved |
|----|------|--------|----------|--------------|----------|
| A1 | | | | | ☐ |

---

## Operator observations

_Free-form; link to postmortem if incident opened._

- Moderation UX:
- DLQ / retry visibility:
- Diagnostics trust:
- Config surprises:

---

## Retry patterns

| Pattern | Seen? | Notes |
|---------|-------|-------|
| Publisher chunk retry then success | | `publish_retries` + success log |
| Publisher retry exhaustion → FAILED | | |
| Telethon FloodWait → recovery | | `telethon_flood_waits` |
| Worker safe re-enqueue | | `worker_retry_safe_reorders` |
| Retry storm (`retry_burst_window`) | | |

---

## Telegram API behavior notes

| Observation | Frequency | Mitigation used |
|-------------|-----------|-----------------|
| FloodWait (collector) | | |
| Transient RPC | | |
| aiogram send delay | | |
| Session reconnect | | |

---

## Diagnostics consistency

| Check | H0 | H+24 | H+48 | H+72 |
|-------|----|------|------|------|
| `schema_version` = 2 | | | | |
| `read_only` true | | | | |
| Findings match logs | | | | |
| False positives noted | | | | |

---

## Daily operational summaries

### Day 1 (hours 0–24)

**Summary:**

**Incidents:**

**Metrics trend:**

### Day 2 (hours 24–48)

**Summary:**

### Day 3 (hours 48–72)

**Summary:**

---

## Stabilization conclusions

| Question | Answer |
|----------|--------|
| 72h without critical incident? | ☐ Yes ☐ No |
| Retry rates stable? | ☐ Yes ☐ No |
| Duplicate publishes? | ☐ None observed |
| Reconnect behavior normal? | ☐ Yes ☐ No |
| Stuck locks / silent failures? | ☐ None |
| Operator workflow sustainable? | ☐ Yes ☐ No |
| Ready for v3.2 planning gate? | ☐ Yes ☐ No → [v3_2_planning_gate.md](../releases/v3_2_planning_gate.md) |

**Recommendation:**

- ☐ Enter steady-state (sign [production_activation_signoff.md](../releases/production_activation_signoff.md))
- ☐ Extend 72h window (reason: ___)
- ☐ Hold v3.2 planning (reason: ___)

**Signed:** Operator ___ Date ___
