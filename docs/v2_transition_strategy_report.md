# v2 transition strategy report

Stewardship assessment — **strategy and tooling only**. No v2 implementation, no runtime contract changes.

## Architectural Preservation Assessment

- [architectural_preservation.md](architecture/architectural_preservation.md) defines invariants, anti-creep rules, and acceptable boundaries.
- [operational_philosophy.md](architecture/operational_philosophy.md) codifies operator-first, bounded automation.
- Frozen contracts remain 14 artifacts / schema v1 / 11 CLIs — verified by `architecture_guardrails.py`.

## Complexity Budget Status

- Framework in [complexity_budget.md](architecture/complexity_budget.md) (6 dimensions, max 30).
- Standing 1.x consumption documented; headroom policy favors proposals ≤8.
- Guardrails emit LOW hints on tool/Makefile proliferation — advisory.

## Long-Term Sustainability Assessment

| Horizon | Posture |
|---------|---------|
| 1–2 years | 1.x maintenance-first; intelligence + scaling discipline |
| 3–5 years | v2 only if [v2_transition_strategy.md](architecture/v2_transition_strategy.md) gates met |
| Default | No rewrite; incremental stewardship |

[maintainer_longevity.md](architecture/maintainer_longevity.md) defines onboarding and minimal viable maintenance.

## Future Scalability Reality Check

[future_scalability_realities.md](architecture/future_scalability_realities.md):

- SQLite: single writer; WAL discipline
- Redis: single-node queue, not HA platform
- Telegram/API limits dominate
- Multi-region / multi-tenant: unsupported

## Technical Debt Governance Status

[technical_debt_governance.md](architecture/technical_debt_governance.md) classifies acceptable, operational, architectural, and “never fix without v2” debt.

## Maintainer Sustainability Assessment

- ADR index + runbooks as knowledge SSOT
- Anti-burnout: maintenance-first, batch releases
- Quarterly guardrails + annual v2 gate review

## Remaining Strategic Risks

| Risk | Mitigation |
|------|------------|
| Accidental v2 scope creep | Evolution matrix + complexity budget |
| Documentation drift | Contract tests + guardrails |
| Operator overload | Capped intelligence; minimal maintenance model |
| False HA deployments | Unsupported registry + env warnings |
| Bus factor | Maintainer onboarding path |

## Recommended Post-v2 Governance

If v2 ever ships:

1. New ADR supersedes preservation policy sections explicitly
2. Parallel 1.x maintenance window ≥6 months
3. Migration + rollback runbooks before tag
4. Keep read-only diagnostics default; no mandatory telemetry
5. `architecture_guardrails.py` extended for v2 contract counts — not replaced by external process

Until then: **remain 1.x production-lite** with stewardship docs and `make architecture-validate`.

## Validation

```bash
make architecture-validate
make ci-test
make release-check
make governance-validate
make scalability-validate
```

## Backward compatibility statement

- No runtime code changes required for this phase
- No hidden v2 implementation
- No evidence format changes
- `tools/architecture_guardrails.py` is read-only advisory
