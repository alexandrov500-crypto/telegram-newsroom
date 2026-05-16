# Long-term support notes (1.0.x)

Community maintenance expectations for the **stable** line. This is **not** an enterprise SLA.

## Additive-only expectations

Within **1.0.x**:

- Optional fields in existing inspection JSON (schema v1 rules).
- New docs, examples, contract tests.
- Bug fixes preserving frozen contracts.

## Schema v1 stewardship

- Inspection artifacts remain at `schema_version: 1`.
- Forward detection of unsupported versions may WARN — not a commitment to adopt v2 in 1.0.x.
- Live app state schemas (`app/versioning`) are separate from frozen `runtime/*.json`.

## Runtime artifact freeze

- No new filenames under `runtime/`.
- Lifecycle order 1–14 unchanged; `runtime_index.json` written last.
- Enforced by `tests/contracts/test_runtime_contracts.py`.

## Operational compatibility

- Makefile targets and CLI commands remain stable.
- `make release-check` before tags.
- Operators may rely on [OPERATOR_QUICKSTART.md](OPERATOR_QUICKSTART.md) and [RUNTIME_LAYOUT_REFERENCE.md](RUNTIME_LAYOUT_REFERENCE.md).

## Dependency upgrade philosophy

- Security patches: yes, with `make release-check`.
- Major ecosystem churn: avoid unless required ([DEPENDENCY_POLICY.md](DEPENDENCY_POLICY.md)).
- Dev tools pinned in `requirements-dev.txt`.

## Supported maintenance scope

| In scope | Out of scope |
|----------|----------------|
| Bug fixes, docs, contract guards | New governance layers |
| Security dependency updates | K8s/Helm/Terraform in-repo |
| Clarifying operator workflows | Managed SaaS control plane |
| Reproducibility improvements | Enterprise SLA / 24×7 support |

## End of 1.0.x

A future **2.0** would require explicit contract revision, ADRs, and migration notes — not silent drift.

See [MAINTENANCE_MODE.md](MAINTENANCE_MODE.md) and [STABILITY_GUARANTEES.md](STABILITY_GUARANTEES.md).
