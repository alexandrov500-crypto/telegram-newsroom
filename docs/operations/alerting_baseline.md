# Operational alerting baseline (production-lite)

Manual/diagnostics-driven alerting — **no mandatory Prometheus**. Operator reviews `make live-telegram-diagnostics` on cadence.

## Review cadence

| Window | Action |
|--------|--------|
| Every 4h (72h window) | Diagnostics JSON + log scan |
| Daily | `make ops-summary` + metrics snapshot |
| On each publish | Quick diagnostics |

## Thresholds

### Reconnect spike

| Field | Threshold | Severity |
|-------|-----------|----------|
| `telethon_reconnects` | >10 / 4h | MEDIUM |
| `session_reset_suspected` | true | HIGH |

**Operator action:** Pause collector; re-auth session if sustained.  
**Escalation:** 30 min if unresolved.  
**False positive:** Single reconnect after network blip — ignore if metrics reset and stable.

---

### Retry amplification

| Field | Threshold | Severity |
|-------|-----------|----------|
| `publish_retries` | >15 / day | MEDIUM |
| `retry_burst_window` | ≥ `RUNTIME_RETRY_STORM_COUNT` (40) | HIGH |

**Operator action:** Stop publish; [RETRY_STORM_RECOVERY.md](../runbooks/RETRY_STORM_RECOVERY.md).  
**Escalation:** Immediate on HIGH.  
**False positive:** CI/soak on same host — use fresh process metrics.

---

### Repeated FloodWait

| Field | Threshold | Severity |
|-------|-----------|----------|
| `telethon_flood_waits` | >5 / session | MEDIUM |
| Log pattern | FloodWait >60s repeatedly | HIGH |

**Operator action:** Increase `PUBLISH_CHANNEL_MIN_INTERVAL_SEC`; pause publishes 15–60 min.  
**Escalation:** 1h if continues.  
**False positive:** One FloodWait during heavy collect — OK if recovered.

---

### Lock contention spike

| Field | Threshold | Severity |
|-------|-----------|----------|
| `publish_lock_contention` | >20 / day | LOW |
| `publish_lock_strict_denied` | >0 with healthy Redis | HIGH |

**Operator action:** Verify single publisher; fix Redis.  
**Escalation:** 15 min on strict_denied in T2.  
**False positive:** Legitimate duplicate job retry — check idempotency keys.

---

### Publish failure ratio

| Field | Threshold | Severity |
|-------|-----------|----------|
| `publish_failures` | >0 with 0 success | MEDIUM |
| Ratio | failures > 50% of attempts | HIGH |

**Operator action:** `DRY_RUN=true`; inspect failed drafts + channel.  
**Escalation:** Before next publish attempt.  
**False positive:** Test draft in staging — exclude from prod ratio.

---

### Session reset frequency

| Field | Threshold | Severity |
|-------|-----------|----------|
| `telegram_api_failures` + reconnects | per diagnostics composite | HIGH |
| Auth errors in log | any `SessionPasswordNeededError` | HIGH |

**Operator action:** [TELETHON_SESSION_LOST.md](../runbooks/TELETHON_SESSION_LOST.md).  
**Escalation:** Immediate — no publish until session valid.  
**False positive:** N/A — treat auth errors as real.

---

## Severity summary

| Severity | Response time | Default action |
|----------|---------------|----------------|
| LOW | Next review | Log + monitor |
| MEDIUM | <4h | Reduce rate / investigate |
| HIGH | Immediate | `DRY_RUN=true` + contain |

## Tooling

```bash
make live-telegram-diagnostics
make live-telegram-diagnostics 2>/dev/null | jq '.findings'
```

Strict staging verify on deploy:

```bash
python3 tools/staging_environment_verify.py --strict
```
