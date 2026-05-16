# Maintenance mode (post-v1.0.0)

**The project is now maintenance-first, not expansion-first.**

Architecture, runtime governance, deployment semantics, and inspection CLIs are **finalized** as of v1.0.0. Ongoing work prioritizes operational longevity, compatibility, and clarity — not new control planes.

## Architecture finalized

- 14 frozen `runtime/*.json` artifacts, lifecycle order 1–14.
- 11 inspection CLI commands; schema `version: 1`.
- Single-node production-lite deployment model.
- See [STABILITY_GUARANTEES.md](STABILITY_GUARANTEES.md) and [architecture/RUNTIME_MATURITY.md](architecture/RUNTIME_MATURITY.md).

## Maintenance priorities

1. **Correctness** — bugs in app pipeline, validation logic, or docs.
2. **Compatibility** — preserve operator scripts, Makefile targets, frozen contracts.
3. **Security** — dependency patches, secret-handling guidance ([SECURITY.md](../SECURITY.md)).
4. **Operator clarity** — docs, examples, reproducible workflows.
5. **Repository health** — contract tests, pinned dev tooling, housekeeping.

## Acceptable changes

- Bug fixes without contract breakage.
- Additive optional JSON fields at schema v1 (per ADR-009).
- Documentation, issue templates, maintenance policy.
- Contract tests that guard existing freeze.
- Conservative dependency security updates ([DEPENDENCY_POLICY.md](DEPENDENCY_POLICY.md)).

## Discouraged changes

- New runtime governance artifacts or inspection subsystems.
- New CLI commands or lifecycle reordering.
- Platform-scale tooling (K8s manifests, orchestration, telemetry stacks).
- Whole-repo style migrations unrelated to a concrete bug.
- “Cleanup refactors” that touch unrelated modules.

## Breaking-change expectations

**1.0.x** should remain compatible for operators:

- Frozen filenames, lifecycle, CLI registry, tri-state enums.
- Breaking changes require **major version** discussion, ADR, and contract test updates.

## Operational compatibility policy

- `make runtime-*` and `python -m newsroom.cli` behavior preserved.
- `make release-check` remains the pre-tag gate.
- Bundle comparison uses `make release-qualify` (not confused with release-check).

## Release cadence philosophy

- Release when there is **operator value** (fixes, security, doc corrections) — not on a feature calendar.
- Patch releases: bugfix + docs + deps.
- No mandatory cadence; **release discipline over deployment automation** ([RELEASE_PROCESS.md](RELEASE_PROCESS.md)).

## Release governance (v1.4)

Upgrade and compatibility policy: [compatibility_policy.md](compatibility_policy.md) · [release_governance.md](release_governance.md) · `make governance-validate` · `python3 tools/release_readiness.py --strict`

## Post-v1 hardening (planning only)

Improvements tracked for **v1.1+** live in [post_v1_hardening.md](post_v1_hardening.md). That roadmap is **opt-in** and does not override the v1.0.0 freeze. Implementation requires ADR acceptance per [architecture/POST_V1_ADR_BACKLOG.md](architecture/POST_V1_ADR_BACKLOG.md).

## Related

- [ISSUE_TRIAGE.md](ISSUE_TRIAGE.md) · [MAINTENANCE_POLICY.md](MAINTENANCE_POLICY.md) · [LTS_NOTES.md](LTS_NOTES.md)
- [post_v1_hardening.md](post_v1_hardening.md) · [POST_V1_TODO_BACKLOG.md](POST_V1_TODO_BACKLOG.md)
- [architecture/ADR-018-post-v1-maintenance-mode.md](architecture/ADR-018-post-v1-maintenance-mode.md)
- [architecture/ADR-019-post-v1-hardening-roadmap-planning-only.md](architecture/ADR-019-post-v1-hardening-roadmap-planning-only.md)
