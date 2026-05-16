# Issue triage

How maintainers classify and respond to reports. **Maintenance-first** — see [MAINTENANCE_MODE.md](MAINTENANCE_MODE.md).

## Categories

| Category | Examples | Typical response |
|----------|----------|------------------|
| **bug** | Crash, wrong validation result, data loss | Fix in app/observability builder; tests |
| **operational issue** | nightly fails, unclear `make` steps | Docs + operator guidance |
| **compatibility issue** | Contract test failure, broken Makefile target | Restore compatibility; no silent breaks |
| **documentation issue** | Wrong path, stale command | Doc fix; link check |
| **enhancement request** | UX improvement within existing model | Evaluate scope; often docs or small additive change |
| **architecture expansion request** | New runtime artifact, orchestration, K8s, telemetry platform | **Exceptional justification required** — usually declined for 1.0.x |

## Architecture expansion requests

Must answer in the issue (see [feature_request.md](../.github/ISSUE_TEMPLATE/feature_request.md)):

1. Why is the **existing operational model** insufficient?
2. Why is **complexity increase** justified?
3. Why can this **not be solved externally** (your fork, wrapper scripts, host tooling)?

Without answers, the issue may be closed as out of scope with pointers to [FAQ.md](FAQ.md) and [STABILITY_GUARANTEES.md](STABILITY_GUARANTEES.md).

## Preferred fixes

- Minimal diff scoped to the reported problem.
- Contract test when touching frozen surfaces.
- Reproduce with `make ci-test` or `make release-check` before PR.
- Update docs when changing operator-visible commands.

## Discouraged complexity growth

- New governance JSON types or validation layers.
- Parallel inspection CLIs for the same concern.
- Deployment automation inside the repo.
- Large dependency additions ([DEPENDENCY_POLICY.md](DEPENDENCY_POLICY.md)).

## Templates

- [Bug report](../.github/ISSUE_TEMPLATE/bug_report.md)
- [Documentation](../.github/ISSUE_TEMPLATE/documentation.md)
- [Operational question](../.github/ISSUE_TEMPLATE/operational-question.md)
- [Feature request](../.github/ISSUE_TEMPLATE/feature_request.md)

## Related

- [SUPPORT.md](../SUPPORT.md) · [CONTRIBUTING.md](CONTRIBUTING.md)
