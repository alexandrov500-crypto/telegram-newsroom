# Production operational baselines

Reference ranges for production-lite T1. Populated from the [72h operational findings](72h_operational_findings.md) window and ongoing diagnostics.

**Sources:** in-process counters (`utils/metrics.py`), `tools/live_telegram_diagnostics.py`, structured logs (`publish.*`, `publisher.chunks_sent`, pipeline tick).

## How to collect

```bash
make live-telegram-diagnostics > var/ops_history/diag_$(date -u +%Y%m%dT%H%MZ).json
# Logs: grep publish.telegram_chunks_duration_sec / publish.success
```

---

## Publish duration

| Measure | Source | Healthy | Warning | Escalation |
|---------|--------|---------|---------|------------|
| Chunk send duration | `publish.telegram_chunks_duration_sec` | p50 <15s, p95 <45s | p95 >60s | p95 >120s or repeated timeout |
| DB finalize | `publish.db_finalize_duration_sec` | <2s | >5s | >10s or `FINALIZE_MISMATCH` |
| End-to-end publish | `record_publish_duration` aggregate | <20s typical | >60s | failure + channel inspect |

**Expected variance:** multi-chunk posts scale linearly; breaking news may skip cadence — annotate separately.

---

## Retry success ratio

| Measure | Formula / proxy | Healthy | Warning | Escalation |
|---------|-----------------|---------|---------|------------|
| Publisher retry rate | Δ`publish_retries` / publish attempts | <0.3 retries/publish | >1.0 | >3.0 or rising 4h trend |
| Retry success | retries with eventual `publish.success` | >80% recover | <50% | storm threshold |

**Note:** Telethon retries are separate (`telethon_flood_waits`, logs `telethon.op_recovered_after_retry`).

---

## Reconnect recovery

| Measure | Source | Healthy | Warning | Escalation |
|---------|--------|---------|---------|------------|
| Reconnect count | `telethon_reconnects` / 24h | 0–3 | 4–10 | >10 or `session_reset_suspected` |
| Recovery time | log gap `telethon_reconnect` → next success | <30s | <5m | >5m or auth errors |

---

## FloodWait frequency

| Measure | Source | Healthy | Warning | Escalation |
|---------|--------|---------|---------|------------|
| Collector FloodWait | `telethon_flood_waits` / 24h | 0–2 | 3–5 | >5 or repeated >60s wait |
| Publisher pacing blocks | `cadence_blocked_publish` | occasional | frequent | blocks > publishes |

---

## Moderation latency

| Measure | Collection | Healthy | Warning | Escalation |
|---------|------------|---------|---------|------------|
| Draft → approve | operator timestamp / bot logs | operator-defined | >2× usual | backlog >24h |
| Approve → channel | publish flow logs | <5m human | >30m | stuck `publishing` >TTL |

_No automated SLA metric in v3.1 — qualitative + log sampling._

---

## Publish / day distribution

| Measure | Healthy (T1 week 1) | Warning | Escalation |
|---------|----------------------|---------|------------|
| Publishes / calendar day | ≤5 (policy) | 6–8 | >8 or burst without approval |
| Publishes / burst window | ≤`PUBLISH_BURST_MAX_MESSAGES` | at cap often | cap + contention |

Config enforcement: `PUBLISH_BURST_*`, `PUBLISH_CHANNEL_MIN_INTERVAL_SEC`, editorial `evaluate_publish_gate`.

---

## Diagnostics noise ratio

| Measure | Definition | Healthy | Warning |
|---------|------------|---------|-----------|
| False positive findings | diagnostics HIGH with no log correlate | 0 | any recurring |
| Status flapping | OK↔WARNING without metric change | rare | >2/day |
| Tool reliability | `make live-telegram-diagnostics` exit 0 | 100% | failures |

---

## Baseline record (post-72h)

| Metric | Observed baseline | Recorded date | Reviewer |
|--------|-------------------|---------------|----------|
| Avg publish duration (s) | | | |
| Retry success ratio | | | |
| Reconnects / day | | | |
| FloodWait / 72h | | | |
| Publishes / day (max) | | | |
| Operator interventions / day | | | |

## Related

- [alerting_baseline.md](alerting_baseline.md)
- [production_safeguards.md](production_safeguards.md)
- [72h_stability_window.md](72h_stability_window.md)
