# Incident postmortem template

Blameless operational learning for production-lite. Use after MEDIUM+ incidents or any rollback ([incident_response.md](../runbooks/incident_response.md)).

**Do not include:** blame-oriented sections, individual performance reviews, or punitive language.

---

## Summary

| Field | Value |
|-------|-------|
| Postmortem ID | PM-YYYY-MM-DD-NN |
| Date | |
| Duration | |
| Severity | LOW / MEDIUM / HIGH / CRITICAL |
| Services affected | collector / publisher / worker / scheduler / bot |
| Operator lead | |

**One-paragraph summary:**

---

## Timeline (UTC)

| Time | Event | Source (log/metric/operator) |
|------|-------|----------------------------|
| | Detection | |
| | Containment | |
| | Rollback action | |
| | Recovery confirmed | |

---

## Detection

- How was the incident noticed?
- Which diagnostics/metrics fired?
- Time to detect (TTD):

---

## Blast radius

| Area | Impact |
|------|--------|
| Telegram channel | |
| Drafts / DB | |
| Queue / Redis | |
| Operator workload | |
| Runtime inspection artifacts | |

---

## Rollback effectiveness

| Action | Executed? | Time to complete | Outcome |
|--------|-----------|------------------|---------|
| `DRY_RUN=true` | | | |
| Process stop | | | |
| Session / DB restore | | | |

**Rollback met <5 min target?** ☐ Yes ☐ No

---

## Operator response

- Actions taken (ordered):
- What worked well:
- What was unclear (docs/runbooks):
- Intervention count:

---

## Recovery validation

- [ ] `make live-telegram-diagnostics` → OK
- [ ] Test publish (DRY_RUN then single live if applicable)
- [ ] No duplicate delivery
- [ ] Metrics returned to baseline ranges ([production_baselines.md](production_baselines.md))

---

## Root cause (technical, blameless)

**Contributing factors:**

**Why existing safeguards did/did not catch it:**

---

## Preventive actions

| Action | Type (doc/runbook/config/process) | Owner | Target date | v3.1-safe? |
|--------|-----------------------------------|-------|-------------|------------|
| | | | | ☐ hotfix ☐ v3.2 |

---

## Governance impact

| Policy | Respected? | Notes |
|--------|------------|-------|
| Publish cap ≤5/day | | |
| Human-in-the-loop | | |
| Freeze policy | | |
| Rollback discipline | | |

**Registry update needed?** ☐ [technical_debt_registry.md](../architecture/technical_debt_registry.md)

---

## Attachments

- Diagnostics JSON paths:
- Log excerpts (redacted):
- Related PM IDs:

---

## Sign-off

| Role | Name | Date |
|------|------|------|
| Operator | | |
| Engineering | | |
