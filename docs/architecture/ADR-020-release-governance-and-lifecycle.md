# ADR-020: Release governance and lifecycle (documentation)

Status: **Accepted (documentation + read-only tooling)**  
Date: 2026-05-15

## Context

v1.0–v1.3 established operational freeze, chaos/soak validation, and production envelope. Without formal governance docs, long-term evolution risks silent contract drift or operator upgrade incidents.

## Decision

- Publish compatibility, deprecation, release governance, migration safety, evidence lifecycle, and feature-flag policies under `docs/`.
- Add upgrade runbooks under `docs/runbooks/upgrades/`.
- Add read-only `tools/release_readiness.py` and `make governance-validate`.
- **No** changes to frozen runtime artifacts, CLI registry, or evidence formats on this ADR alone.

## Consequences

- **Positive:** Predictable upgrades and maintainer gates.
- **Positive:** Zero silent removal policy explicit.
- **Negative:** Maintainers must keep flag registry in sync with docs/tool.
- **Negative:** Minor releases require more checks than patch.

## Non-goals

- Release automation bots, K8s, mandatory external observability
- Changing `make release-check` semantics without ADR

## Related

- [compatibility_policy.md](../compatibility_policy.md) · [release_governance.md](../release_governance.md)
