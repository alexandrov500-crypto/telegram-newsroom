# Maintenance branch policy (v3.2 stewardship)

Git workflow after tooling freeze tag `v3.2-operational-tooling-freeze`.

## Allowed branch types

| Branch pattern | Use |
|----------------|-----|
| `main` / `master` | Stabilization line (protected) |
| `hotfix/ops-*` | Tooling/docs hotfixes only |
| `docs/ops-*` | Documentation-only |
| `chore/ops-*` | Tests, CI, reproducibility |

## Forbidden branch purposes

- `feature/ops-dashboard`, `feat/telemetry-*` — rejected at review
- Long-lived `experiment/*` ops branches without ADR

## Hotfix naming

```
hotfix/ops-<issue>-<short-description>
```

Example: `hotfix/ops-42-archive-verify-gzip`

## Freeze branch protection expectations

- Require `make stewardship-audit-validate` on tooling PRs (or full `stewardship-validate` for large changes)
- No force-push to tags matching `v3.2-operational-tooling-freeze`
- Runtime changes require separate review path and must not ride ops hotfix PRs

## ADR escalation conditions

New ADR (035+) required when proposal includes:

- New persistent store for ops data
- Live/network coupling in export/validate path
- Runtime hooks or publish-path instrumentation
- New Makefile target that starts daemons

## Release tagging policy

| Tag kind | When |
|----------|------|
| `v3.2-operational-tooling-freeze` | **Immutable** — do not move |
| `v3.2-ops-tooling-patch-N` | Optional docs/tooling patch (release manager) |
| Runtime tags | Separate process (`v3.1-production-lite`, etc.) |

## Archival branches

- Keep `v3-live-telegram-validation` until merged; then archive per team policy
- Do not delete tags referenced in [v3_2_final_manifest.md](../releases/v3_2_final_manifest.md)

## When to start v4 (or ADR-035+ program)

Start only if **all** apply:

- Documented operator pain not solvable by existing kits
- ADR approved with explicit non-goals reviewed
- Runtime isolation proof in design
- `make stewardship-audit-validate` extended for new scope

## When NOT to start v4

- “Nice dashboard” requests
- Real-time metrics envy
- Competitor feature parity
- Refactor for refactor’s sake
- Single operator convenience without governance review

## References

- [stewardship_state_declaration.md](../releases/stewardship_state_declaration.md)
- [maintenance_hotfix_procedure.md](../runbooks/maintenance_hotfix_procedure.md)
