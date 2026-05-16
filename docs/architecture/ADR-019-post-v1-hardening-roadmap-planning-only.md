# ADR-019: Post-v1 hardening roadmap (planning-only)

Status: **Accepted (documentation scope only)**  
Date: 2026-05-15  
Branch: `post-v1-hardening`

## Context

v1.0.0 completed burn-in validation ([BURN_IN_REPORT.md](../BURN_IN_REPORT.md)). Operators need a **forward-looking** hardening plan without reopening the frozen runtime governance model (ADR-015–018).

## Decision

- Publish [post_v1_hardening.md](../post_v1_hardening.md) as the SSOT for post-v1 operational improvements.
- Maintain [POST_V1_TODO_BACKLOG.md](../POST_V1_TODO_BACKLOG.md) and [POST_V1_ADR_BACKLOG.md](POST_V1_ADR_BACKLOG.md).
- Store RFC drafts under [../rfc/](../rfc/) — proposals only.
- **No** runtime behavior, artifact, or CLI registry changes on the planning branch except contract tests guarding doc presence.

## Consequences

- **Positive:** Clear separation between maintenance (ADR-018) and future opt-in hardening.
- **Positive:** Audit findings are traceable without implying v1.0.0 defects.
- **Negative:** Maintainers must reject PRs that implement P2/P3 items without accepted child ADRs.
- **Negative:** Risk of scope creep if proposals bypass triage ([ISSUE_TRIAGE.md](../ISSUE_TRIAGE.md)).

## Non-goals

- Implementing RFC proposals on this ADR alone.
- Changing `VERSION`, `RELEASE_STATUS`, or frozen contracts.
- Mandating Prometheus, Kubernetes, or new runtime JSON files.

## Related

- [ADR-018-post-v1-maintenance-mode.md](ADR-018-post-v1-maintenance-mode.md)
- [POST_V1_ADR_BACKLOG.md](POST_V1_ADR_BACKLOG.md)
