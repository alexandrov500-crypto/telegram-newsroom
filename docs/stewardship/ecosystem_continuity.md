# Ecosystem continuity model

How the project stays coherent across people, time, and low activity.

## Maintainer continuity

- Onboarding: [maintainer_longevity.md](../architecture/maintainer_longevity.md) + [START_HERE.md](../START_HERE.md)
- ADR index SSOT: [architecture/README.md](../architecture/README.md)
- Handoff artifact: latest validation report + CHANGELOG unreleased section

## Operator continuity

- Daily: `make runtime-help`, nightly inspection
- Under stress: runbooks → semantics forbidden states → guardrails tools
- No requirement for original author contact

## Release continuity

- `make release-check` before tag
- Upgrade runbooks under `docs/runbooks/upgrades/`
- Compatibility policy unchanged unless major version

## Governance continuity

- `make governance-validate`
- Feature flag registry in `feature_flag_governance.md`
- Semantics/architecture/history guardrails (read-only)

## Recovery continuity

- Same 12 required artifacts + validate-recovery
- Recovery semantics: [recovery_semantics.md](../semantics/recovery_semantics.md)
- Degraded modes explicit (WARN ≠ broken)

## Documentation continuity

- Single entry: START_HERE
- Phase reports linked from CHANGELOG
- Stewardship docs for archaeology

## Continuity under low activity

| Practice | Frequency |
|----------|-----------|
| Dependency security check | Monthly |
| Read CHANGELOG + ADR index on return | Each return |
| `make ci-test` before any merge | Each change |
| Skim `history_guardrails.py` output | Quarterly |

Low activity is normal; **frozen contracts protect dormant periods**.

## Continuity after dormancy

1. Read [release_archaeology.md](release_archaeology.md) for phase context
2. Run `make traceability-validate` + `make release-check`
3. Compare local deploy to `unsupported_deployments.md`
4. Re-enable opt-in flags deliberately, not all at once
5. Run recovery drill before scaling workers

Dormancy does not justify skipping quiesce on restore.
