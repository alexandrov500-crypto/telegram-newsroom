# Release governance

How maintainers cut releases without contract drift or operator surprise.

## Release classes

| Class | Version bump | Scope | Gates |
|-------|--------------|-------|-------|
| **Patch** | `v1.0.z` | Bugfix, security, docs | `make release-check` |
| **Minor** | `v1.y.0` | Opt-in features default off, additive JSON | release-check + chaos + soak + readiness |
| **Operational** | Tag optional | Deploy/config/runbooks only | `make ci-test` + operator checklist |
| **Experimental** | Branch / pre-release | Flags documented experimental | chaos subset; not for production default |

## Release phases

1. **Development** — feature branches; contract tests green on PR.
2. **Freeze candidate** — CHANGELOG drafted; no new frozen artifacts.
3. **Validation** — burn-in checklist optional for operational; required gates below for minor.
4. **Tag** — signed tag `vX.Y.Z`; GitHub release notes from CHANGELOG.
5. **Post-release** — maintenance matrix weekly tasks resume.

## Freeze checkpoints

Before any **minor** tag:

- [ ] No new `runtime/*.json` filenames
- [ ] No new inspection CLI commands
- [ ] `observability/runtime_contracts.py` unchanged counts (readiness tool)
- [ ] ADR if governance docs change semantics

## Burn-in requirements

- **Patch:** not required.
- **Minor (production deploy):** operator-run [BURN_IN_REPORT.md](BURN_IN_REPORT.md) recommended 7-day checklist on staging.
- **Major:** burn-in + explicit sign-off.

## Chaos validation requirements

| Class | Requirement |
|-------|-------------|
| Patch | Optional |
| Minor | `make chaos-test` green |
| Operational | N/A |
| Experimental | `make chaos-test` on PR |

## Soak validation requirements

| Class | Requirement |
|-------|-------------|
| Patch | Optional |
| Minor | `make soak-test` green |
| Operational | N/A |

## Release gate rules

**Patch minimum:**

```bash
make ci-test
make release-check
```

**Minor minimum:**

```bash
make ci-test
make release-check
make chaos-test
make soak-test
python3 tools/release_readiness.py --strict
```

**Operational:** `make ci-test` + upgrade runbook executed on staging.

## Rollback requirements

- Pre-change: `backup_cli` + `runtime_snapshot.sh` ([migration_safety.md](migration_safety.md)).
- Rollback runbook: [runbooks/upgrades/SAFE_ROLLBACK.md](runbooks/upgrades/SAFE_ROLLBACK.md).
- Re-verify: `make verify-runtime` on restored inspection tree.

## Operator sign-off checklist

- [ ] CHANGELOG reviewed for deprecations
- [ ] `.env` diff reviewed (no accidental flag flip)
- [ ] `OUTPUT_DIR` snapshot taken
- [ ] DB backup if schema migration (app layer only)
- [ ] Post-deploy: `runtime-index` + `verify-runtime` WARNING/OK understood

## Related

- [RELEASE_PROCESS.md](RELEASE_PROCESS.md) · [RELEASE_CHECKLIST.md](RELEASE_CHECKLIST.md) · [compatibility_policy.md](compatibility_policy.md)
