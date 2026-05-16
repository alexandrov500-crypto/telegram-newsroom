# Preservation governance

How preservation strategy evolves without archival bureaucracy.

## When preservation strategy updates

- Python floor change in `pyproject.toml`
- Critical dependency pin strategy change
- New unsupported recovery scenario discovered
- Major external API breakage documented

Updates: PR to `docs/preservation/*` + CHANGELOG + optional ADR note.

## Ecosystem aging review cadence

| Cadence | Action |
|---------|--------|
| Quarterly | `preservation_guardrails.py` + skim ecosystem_aging.md |
| Annual | Long-horizon recovery tabletop; dependency pin review |
| On CVE | Patch pin + security-validate |

## Dependency sunset policy

- Do not remove optional deps without ADR unless unused in tree.
- Postgres drivers may remain for future path — document optional status.
- Sunset = stop recommending, not emergency deletion without migration note.

## EOL response policy

| EOL type | Response |
|----------|----------|
| Python | Uplift branch; update requires-python |
| Redis/Telethon/OpenAI | Pin bump + integration tests |
| Frozen runtime schema | v2 program only |

## Archival continuity expectations

Operators archive (out of repo):

- Git tag name
- sqlite file
- OUTPUT_DIR snapshot
- Redacted env template

Repo preserves **how** to recover, not production secrets.

## Long-term stewardship boundaries

| In scope | Out of scope |
|----------|--------------|
| Docs + read-only guardrails | Full reproducible-build program |
| Pin discipline | Vendoring PyPI |
| Recovery honesty | Enterprise archive appliance |
| Traceability linkage | Contributor bureaucracy platform |

## Validation

```bash
make preservation-validate
make traceability-validate
```

## Relation to other governance

- Architecture: [v2_transition_strategy.md](../architecture/v2_transition_strategy.md)
- Semantics: [semantics_governance.md](../semantics/semantics_governance.md)
- History: [decision_archaeology_index.md](../stewardship/decision_archaeology_index.md)
