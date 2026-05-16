# Operational history preservation

What historical signal to keep — and what to discard — for audit-friendly stewardship.

## What operational history matters

| Category | Preserve | Where |
|----------|----------|-------|
| Release decisions | ADRs, CHANGELOG, validation reports | `docs/architecture/`, `docs/` |
| Inspection evidence | Nightly OUTPUT_DIR snapshots (bounded) | Operator storage |
| Recovery drills | Drill outputs, compare-baseline | `examples/failure_drills/` (samples) |
| Config discipline | `.env.example`, flag governance | Repo |
| Incident learnings | Runbook updates, semantics forbidden states | `docs/runbooks/`, `docs/semantics/` |
| Stewardship lineage | This directory | `docs/stewardship/` |

## What should NOT be preserved (in-repo)

- Full production Telegram message archives
- Unredacted secrets or tokens
- Unbounded CI log dumps in git
- Per-job stdout forever
- Personal operator notes without redaction
- Duplicate copies of same nightly without retention policy

## Retention expectations

| Asset | Guidance |
|-------|----------|
| `OUTPUT_DIR` | Prune per `evidence_lifecycle.md` / tools |
| Git history | Native git; no rewrite |
| ADRs | Permanent; supersede, don’t delete |
| RFCs rejected | Keep as archaeology |
| Validation reports | Keep; mark phase in report header |

## Historical evidence boundaries

- Frozen **runtime/** JSON defines inspection truth for a point in time
- Reports document **what was validated**, not production SLA
- `var/ops_history/` optional operator trend samples — not repo-required

## Recovery-history expectations

- Record **that** drill ran and PASS/WARN/FAIL — not every byte copied
- `validate-recovery` output storable in ticket/archive
- Do not rely on Redis alone for long-term recovery proof

## Audit-history expectations

- Audit-friendly = ADR + manifest + verify-runtime trail
- Not SOC2 binder — no control framework in-repo
- `audit_snapshot.json` is operational inspection, not financial audit

## Bounded preservation rule

If preservation cost > operator value for 12 months → external archive or delete per retention tool.
