# Incident response (production-lite)

Classification, containment, rollback, recovery validation. **Human escalation** — no auto-remediation.

## Global containment (any HIGH)

1. `DRY_RUN=true` → restart services
2. `make live-telegram-diagnostics` → save JSON
3. Notify operator lead
4. Do not resume publish until recovery validation passes

---

## Telegram API instability

| Phase | Action |
|-------|--------|
| **Detection** | `telegram_api_failures` ↑; send errors in logs |
| **Containment** | `DRY_RUN=true`; pause scheduler tick |
| **Rollback** | Stop publish; keep collector off if unstable |
| **Recovery** | Test connect; one DRY_RUN publish; one live publish |
| **Postmortem** | Timeline, metrics snapshot, Telegram status |

---

## Redis unavailable

| Phase | Action |
|-------|--------|
| **Detection** | `publish_lock_strict_denied`; Redis PING fail |
| **Containment** | Stop extra workers; single node only |
| **Rollback** | T1 mode: `REDIS_ENABLED=false` only if single worker |
| **Recovery** | Restore Redis; `PUBLISH_LOCK_STRICT=1`; chaos lock test |
| **Postmortem** | Why Redis down; fallback events |

---

## Session corruption

| Phase | Action |
|-------|--------|
| **Detection** | Telethon load errors; invalid session |
| **Containment** | Stop collector |
| **Rollback** | Restore session file from backup |
| **Recovery** | `TELEGRAM_LIVE_VALIDATE=1` connect test |
| **Postmortem** | [TELETHON_SESSION_LOST.md](TELETHON_SESSION_LOST.md) |

---

## Stuck retries

| Phase | Action |
|-------|--------|
| **Detection** | `retry_burst_window` high; queue depth growth |
| **Containment** | Pause worker; `DRY_RUN=true` |
| **Rollback** | [RETRY_STORM_RECOVERY.md](RETRY_STORM_RECOVERY.md) |
| **Recovery** | Drain DLQ manually; safe retry verified |
| **Postmortem** | Root cause: OpenAI vs Telegram vs worker |

---

## Duplicate publish suspicion

| Phase | Action |
|-------|--------|
| **Detection** | Channel duplicate; contention metrics |
| **Containment** | `DRY_RUN=true` immediately |
| **Rollback** | Halt all publishers |
| **Recovery** | DB/channel reconcile; lock test |
| **Postmortem** | [publish_idempotency.md](../operations/publish_idempotency.md) |

---

## Diagnostics inconsistency

| Phase | Action |
|-------|--------|
| **Detection** | Tool errors; metrics don't match logs |
| **Containment** | Treat as unknown state — `DRY_RUN=true` |
| **Rollback** | Restart process (reset in-memory metrics) |
| **Recovery** | Re-run diagnostics; compare to logs |
| **Postmortem** | Version skew? mixed hosts? |

---

## Postmortem requirements (MEDIUM+)

- Start/end time (UTC)
- Metrics JSON attachment
- Config diff (redacted)
- Operator actions timeline
- Customer/channel impact
- Preventive action (doc/runbook update)

## Escalation timing

| Severity | Max time to contain |
|----------|---------------------|
| HIGH | 15 minutes |
| MEDIUM | 4 hours |
| LOW | Next scheduled review |
