# Production safeguards

Enforcement map for production-lite. **No autonomous scaling** — safeguards are config + code paths + operator policy.

## Config-enforceable limits

| Safeguard | Config / code | Production-lite default |
|-----------|---------------|-------------------------|
| Publish spacing | `PUBLISH_CHANNEL_MIN_INTERVAL_SEC` | ≥0.75s (profile `production`) |
| Burst cap | `PUBLISH_BURST_MAX_MESSAGES` + `PUBLISH_BURST_WINDOW_SEC` | ≤6 per window (max window 3600s) |
| Profile clamps | `APP_DEPLOYMENT_PROFILE=production` | tightens burst/interval |
| Dry run | `DRY_RUN=true` | blocks all sends |
| Editorial gate | `evaluate_publish_gate` + policy JSON | quiet hours, min interval, burst |
| Chunk retry ceiling | `publisher/retry.py` | 3 attempts / chunk |
| Telethon retry ceiling | `TELETHON_OP_MAX_ATTEMPTS` (default 4) | collector |
| Lock TTL | `publish_draft_lock` | 180s Redis EX |
| Strict lock | `PUBLISH_LOCK_STRICT` + `REDIS_ENABLED` | T2 only |

**Operational publish/day cap (≤5):** enforced by operator policy + burst/min-interval config during first week; not a separate env key (governance constraint — avoid silent code changes).

---

## Safeguard reference

### Publish volume cap (operational + burst)

| | |
|--|--|
| **Trigger** | Operator attempts >5 publishes/day week 1 |
| **Expected behavior** | Operator stops; cadence may block via `publish_gate_burst_cap` |
| **Rollback** | `DRY_RUN=true` |
| **Escalation** | Lead operator; review `cadence_blocked_publish` |

**Config tuning (example T1):**

```env
APP_DEPLOYMENT_PROFILE=production
PUBLISH_CHANNEL_MIN_INTERVAL_SEC=300
PUBLISH_BURST_WINDOW_SEC=3600
PUBLISH_BURST_MAX_MESSAGES=5
```

---

### Retry ceiling

| | |
|--|--|
| **Trigger** | `publish_retries` or `telethon_flood_waits` rising |
| **Expected behavior** | Bounded retries then fail; draft `FAILED` |
| **Rollback** | Pause publish; `DRY_RUN=true` |
| **Escalation** | [retry_error_matrix.md](retry_error_matrix.md); inspect logs |

---

### FloodWait pause

| | |
|--|--|
| **Trigger** | `telethon_flood_waits` >5 or repeated FloodWait logs |
| **Expected behavior** | Sleep `max(seconds, base×attempt)`; no tight loop |
| **Rollback** | Stop collector tick; increase intervals |
| **Escalation** | Manual cooldown 15–60 min |

---

### Lock timeout / contention

| | |
|--|--|
| **Trigger** | `publish_lock_contention` elevated; publish hangs |
| **Expected behavior** | Second worker gets `ALREADY_HANDLED`; TTL expires after 180s |
| **Rollback** | Single worker; fix Redis |
| **Escalation** | [publish_idempotency.md](publish_idempotency.md) TTL section |

---

### Duplicate publish prevention

| | |
|--|--|
| **Trigger** | Double job / double-click |
| **Expected behavior** | Lock + DB status → `ALREADY_HANDLED` |
| **Rollback** | `DRY_RUN=true`; channel inspect |
| **Escalation** | Manual reconcile if messages duplicated |

---

### Operator confirmation path

| | |
|--|--|
| **Trigger** | Any publish |
| **Expected behavior** | Human approves in admin bot; no headless auto-publish in T1 |
| **Rollback** | Disable worker publish handler / `DRY_RUN` |
| **Escalation** | Review moderation fatigue notes |

---

### Safe shutdown

| | |
|--|--|
| **Trigger** | Deploy, maintenance |
| **Expected behavior** | SIGTERM → drain; lock released in `finally` or TTL |
| **Rollback** | Wait TTL before restart publish |
| **Escalation** | Check stuck `publishing` drafts |

---

## Verification commands

```bash
make live-telegram-diagnostics
python3 -c "from app.config import load_settings; s=load_settings(); print(s.dry_run, s.publish_channel_min_interval_sec, s.publish_burst_max_messages)"
```

## Related

- [alerting_baseline.md](alerting_baseline.md)
- [incident_response.md](../runbooks/incident_response.md)
