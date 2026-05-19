# Long-horizon custodian notes

Brief guidance for **years** of passive continuity. Not a runbook.

---

## If the system is quiet

**Do not optimize it.**

Quiet logs, invisible digest, empty intervention weeks are **success**.

---

## If the system is stable

**Do not redesign it.**

Stable validation summaries are not an invitation to “improve” governance or architecture.

---

## If validation remains calm

**Prefer observation over intervention.**

```bash
python3 scripts/weekly_runtime_validation.py --record   # optional but sufficient
python3 scripts/monthly_stability_review.py             # monthly
```

Record in [weekly_non_intervention_log.md](weekly_non_intervention_log.md) when untouched.

---

## If intervention is necessary

Keep it:

- **bounded** — smallest fix that resolves evidence  
- **reversible** — rollback path clear  
- **survivability-oriented** — restore operation, not elegance  
- **architecture-preserving** — no new layers; see [maintenance_thresholds.md](maintenance_thresholds.md)  

Document evidence in [STEADY_STATE_STATUS.md](STEADY_STATE_STATUS.md) and weekly baseline.

---

## 12–24 month expectation

Newsroom should:

- stay calm without redesign  
- avoid governance evolution pressure  
- not accumulate unbounded entropy  
- remain understandable and transferable  
- run with **minimal** engineering involvement  

---

## When in doubt

Read [TERMINAL_STEWARDSHIP_NOTE.md](TERMINAL_STEWARDSHIP_NOTE.md) — then do nothing unless risk is clear.

---

## Final custodian expectation (archive phase)

If the infrastructure **continues operating calmly**, the correct stewardship action is usually **no action**.

Calm validation, quiet digest, and months without commits are **consistent with** `ARCHIVED_CONTINUITY` — not a signal to “wake up” the architecture.

Do not intervene because inactivity feels uncomfortable. Intervene only when [maintenance_thresholds.md](maintenance_thresholds.md) and evidence require it.

Archive boundary: [stewardship_archive_boundary.md](stewardship_archive_boundary.md).

---

## Related

- [PASSIVE_CONTINUITY_DECLARATION.md](PASSIVE_CONTINUITY_DECLARATION.md)
- [hibernation_readiness.md](hibernation_readiness.md)
