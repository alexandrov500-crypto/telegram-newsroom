# Production-lite governance audit

Periodic review that v3.1 operational constraints remain enforced. **Audit date:** 2026-05-16 (initial, post-activation). **Next review:** +30 days or after any HIGH incident.

## Audit scope

- Branch/tag: `v3.1-production-lite`
- Tier: T1 single-operator production-lite
- Frozen runtime contracts: unchanged

---

## Control assessment

| Control | Expected | Evidence | Status |
|---------|----------|----------|--------|
| Publish caps respected | ≤5/day week 1; burst config enforced | Operator log; `cadence_blocked_publish`; config review | ☐ PASS ☐ FAIL ☐ N/A |
| Rollback tested recently | `DRY_RUN` drill <30 days | [controlled_activation.md](../runbooks/controlled_activation.md) checkpoint | ☐ PASS |
| Diagnostics reviewed regularly | Every 4h in 72h; daily after | `var/ops_history/` or ops notes | ☐ PASS |
| Operator workload sustainable | No burnout signals | [operator_staging_signoff.md](../staging/operator_staging_signoff.md) + 72h notes | ☐ PASS |
| Moderation bottlenecks | Acceptable latency | Qualitative in 72h findings | ☐ PASS |
| Retry storms absent | `retry_burst_window` below storm | Diagnostics history | ☐ PASS |
| No silent failures | FAILED drafts + logs | DB + channel spot check | ☐ PASS |
| No duplicate publishes | Channel audit | Lock metrics + manual | ☐ PASS |

---

## Config verification

```bash
python3 tools/staging_environment_verify.py --strict
python3 -c "from app.config import load_settings as l; s=l(); print(s.dry_run, s.publish_burst_max_messages, s.publish_channel_min_interval_sec, s.publish_lock_strict)"
```

| Setting | Expected T1 | Observed |
|---------|-------------|----------|
| `DRY_RUN` | false (steady) | |
| `APP_DEPLOYMENT_PROFILE` | production | |
| `PUBLISH_BURST_MAX_MESSAGES` | ≤5–6 | |
| `REDIS_ENABLED` | false (T1) | |
| `PUBLISH_LOCK_STRICT` | false (T1) | |

---

## Process verification

| Process | Documented | Followed |
|---------|------------|----------|
| Incident response | [incident_response.md](../runbooks/incident_response.md) | ☐ |
| Postmortem (if incidents) | [postmortem_template.md](../operations/postmortem_template.md) | ☐ |
| Freeze policy | [stabilization_freeze_policy.md](stabilization_freeze_policy.md) | ☐ |
| 72h findings | [72h_operational_findings.md](../operations/72h_operational_findings.md) | ☐ |

---

## Findings

| ID | Gap | Severity | Action |
|----|-----|----------|--------|
| G1 | | | |

---

## Audit conclusion

| Result | |
|--------|--|
| Overall | ☐ COMPLIANT ☐ COMPLIANT WITH NOTES ☐ NON-COMPLIANT |
| v3.2 planning authorized | ☐ Yes ☐ No — see [v3_2_planning_gate.md](../releases/v3_2_planning_gate.md) |

**Auditor:** ___ **Date:** ___
