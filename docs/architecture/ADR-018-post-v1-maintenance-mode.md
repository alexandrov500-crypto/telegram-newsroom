# ADR-018: Post-v1 maintenance mode

Status: Accepted  
Date: 2026-05-15

Scope: maintenance documentation, GitHub templates, contract tests. **No runtime, governance, deployment, or CLI changes.**

## Context

v1.0.0 declared stable operational freeze (ADR-017). Without explicit maintenance discipline, contributors may reopen “architecture construction” via issues and PRs — reintroducing governance proliferation, dependency churn, and operator confusion.

## Decision

- Adopt **maintenance-first, not expansion-first** as the default mode ([MAINTENANCE_MODE.md](../MAINTENANCE_MODE.md)).
- Publish issue triage, LTS notes, dependency policy, and GitHub templates.
- Add `tests/contracts/test_maintenance_docs.py` to guard docs and freeze wording.
- Continue architecture freeze; stewardship via compatibility and contract tests.

## Consequences

- **Positive:** Clear expectations for bugs vs architecture expansion.
- **Positive:** Lower maintenance overhead — fewer ambiguous PRs.
- **Negative:** Valid platform features may be declined or deferred to external tooling.
- **Negative:** Maintainers must enforce scope consistently.

## Non-goals

- Enterprise SLA or paid support program.
- New runtime JSON, orchestration, telemetry, plugins, deployment bots.
- Expanding architecture taxonomy or inspection CLI surface.
