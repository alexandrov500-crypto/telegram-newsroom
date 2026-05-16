# Terminal state preservation addendum

Addendum to [repository_terminal_state.md](repository_terminal_state.md) and ADR-037. Clarifies archival authority when restart is discussed.

## Canonical baseline

| Artifact | Authority |
|----------|-----------|
| `v3.2-operational-tooling-freeze` | Tooling code immutability anchor (`ab7c92a`) |
| `v3.2-archival-baseline` | Archival publication anchor (`0e134a2`) |
| [v3_2_publication_manifest.md](v3_2_publication_manifest.md) | Inventory and entry points |

**These remain canonical for the v3.2 era regardless of future programs.**

## Restart does not supersede archival guarantees

A approved restart program:

- **Must not** rewrite v3.2 history or retag freeze commits
- **Must not** delete certification or closure documents
- **Must** add new ADR numbers (038+), not renumber 030–037
- **Must** preserve `make archival-freeze-validate` meaning for v3.2 checkout

New work is **additive in time**, not replacement in history.

## Historical auditability

Future maintainers must be able to:

1. Checkout `v3.2-archival-baseline`
2. Run documented validation chain
3. Regenerate fingerprints/seals under `OPS_FROZEN_UTC`
4. Read closure reports and understand **why** terminal state was declared

## Immutable tags

Tags listed above are **authoritative**. Moving tags requires:

- Written governance exception
- New tags documenting the move (never silent force-push)

## Archival lineage

```
876e1b9 P1 → 963bdf0 P2 → ab7c92a P3–FINAL
  → v3.2-operational-tooling-freeze
  → 0e134a2 archival closure → v3.2-archival-baseline
```

No future ADR may claim this lineage did not occur.

## References

- [ADR-037](../architecture/ADR-037-governance-restart-framework.md)
- [preservation_priority_policy.md](../governance/preservation_priority_policy.md)
