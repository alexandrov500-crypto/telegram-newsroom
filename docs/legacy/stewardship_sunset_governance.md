# Stewardship sunset governance

How stewardship **scales down** without governance inflation or abandonment theater.

## Stewardship scale-down ladder

| Stage | Governance surface |
|-------|-------------------|
| Full | All validate targets; active development |
| Legacy active | ci-test, release-check, governance-validate on release |
| Legacy passive | preservation + legacy validate quarterly |
| Dormant | Operator-driven; repo docs are SSOT |

## Governance simplification rules

- **Do not add** new guardrails tools without retiring or merging overlap.
- **Do not add** parallel policy docs — update SSOT ([long_term_readability.md](../stewardship/long_term_readability.md)).
- **Do not add** default-on flags in passive stage.
- **Keep** frozen contract tests — they are the shrink-wrap.

## Dormant-project handling

| Do | Don't |
|----|-------|
| Keep repo public/readable | Delete ADRs |
| Pin last tag in README (optional) | Rewrite git history |
| Document status in CHANGELOG | Remove tests |
| Archive operator backups externally | Convert repo to empty shell |

## Final maintenance expectations

When in maintenance-only:

- CVE fixes > features
- Doc clarity > new phase reports
- One-line CHANGELOG entries
- ADR only if semantics/contract truth changes

## Release freeze expectations

**Soft freeze:** no releases until needed — not prohibited.

**Hard freeze (optional maintainer declaration):**

- Only PATCH from last tag
- No new ADRs except corrections
- v2 program document only path for contract break

Freeze is **declarative** in maintainer notes — no automation.

## Archive transition guidance

Transition to “operator archive + repo docs” model:

1. Publish final tag
2. Run full validation suite; save reports optional
3. Hand off [controlled_sunset.md](controlled_sunset.md) checklist
4. Stop promising `main` compatibility — point to tag

**Not required:** separate archive repository, compliance binder, or shutdown bot.

## Relation to preservation

- [preservation_governance.md](../preservation/preservation_governance.md) — dependency/aging
- This doc — human/process scale-down

## Validation

```bash
make legacy-validate
make preservation-validate
make traceability-validate
```
