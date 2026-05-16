# Maintainer longevity & succession

Keep the project maintainable by small teams over 3–5 years.

## Maintainer onboarding

Recommended first-week path:

1. [START_HERE.md](../START_HERE.md) → [ENGINEERING_PHILOSOPHY.md](../ENGINEERING_PHILOSOPHY.md)
2. `make demo-runtime` / `make runtime-help`
3. [RUNTIME_CONTRACTS.md](RUNTIME_CONTRACTS.md) — frozen artifacts
4. Run `make ci-test` and `make release-check`
5. Read ADR index ([README.md](README.md)) — newest last
6. Shadow one nightly inspection + recovery drill

## Institutional knowledge retention

| Asset | Purpose |
|-------|---------|
| ADRs | Why decisions were made |
| Runbooks | How to recover |
| Validation reports (`v1_*_report.md`) | What was proven |
| Makefile targets | Executable operator map |

**Do not rely on chat history.** If it matters, it is in repo docs or ADR.

## ADR discipline

- One decision per ADR
- Status: Proposed → Accepted → Superseded
- Link related docs in ADR index table
- Planning-only ADRs clearly marked (ADR-019 pattern)

## Roadmap continuity

- [post_v1_hardening.md](../post_v1_hardening.md) — ideas, not commitments
- [POST_V1_ADR_BACKLOG.md](POST_V1_ADR_BACKLOG.md) — not accepted until ADR
- v2 only via [v2_transition_strategy.md](v2_transition_strategy.md)

Avoid duplicate roadmaps; extend existing docs.

## Governance continuity

Release of record:

```bash
make governance-validate
make release-readiness
make architecture-validate   # v2 stewardship
```

Feature flags: [feature_flag_governance.md](../feature_flag_governance.md) is SSOT.

## Anti-burnout guidance

- Default to **maintenance-first** ([MAINTENANCE_MODE.md](../MAINTENANCE_MODE.md))
- Reject scope that fails complexity budget
- No on-call for optional subsystems
- Batch releases; avoid continuous flag churn
- Use read-only tools before writing new code

## Minimal viable maintenance

Monthly:

- Dependency security review (`make security-validate`)
- Disk/retention on `OUTPUT_DIR`
- One recovery drill or validate-recovery

Per release:

- `make release-check`
- CHANGELOG user-visible entries only

Quarterly:

- Architecture guardrails + v2 gate review
- Technical debt class scan

This is sufficient for production-lite health if operators run nightly inspection.
