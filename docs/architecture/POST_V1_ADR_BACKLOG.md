# Post-v1 architecture decision backlog

**Status:** Proposed ADRs only — none accepted for implementation until reviewed after a v1.0.x patch window.

Parent plan: [../post_v1_hardening.md](../post_v1_hardening.md). Planning ADR: [ADR-019-post-v1-hardening-roadmap-planning-only.md](ADR-019-post-v1-hardening-roadmap-planning-only.md).

| ID | Title | Priority | Operational impact | Migration risk | Depends on |
|----|-------|----------|--------------------|----------------|------------|
| ADR-019 | Post-v1 hardening roadmap (planning-only) | — | None (docs) | None | ADR-018 |
| ADR-020 | Unified retry and error classification policy | P1 | Fewer silent retries / inconsistent DLQ | Low | — |
| ADR-021 | Worker delivery semantics (at-least-once vs safe-retry) | P1 | Job loss prevention | Medium | ADR-020 |
| ADR-022 | Publish lock strict mode and Redis fallback | P1 | Duplicate publish prevention | Low | — |
| ADR-023 | Opt-in extended metrics export | P2 | Better incident triage | Low | — |
| ADR-024 | Deep health profiles (liveness vs dependency) | P2 | Faster misconfig detection | Low | — |
| ADR-025 | Queue backend abstraction (memory/redis) | P3 | Horizontal worker scale | Medium | ADR-003 boundary |
| ADR-026 | Pluggable storage and intelligence backends | P3 | Multi-node state | High | ADR-025 |
| ADR-027 | PostgreSQL as optional production profile | P3 | Write scalability | High | ADR-026 |
| ADR-028 | Multi-channel publishing model | P3 | Product scope | Medium | ADR-022 |
| ADR-029 | Secrets provider interface | P2 | Security posture | Medium | — |
| ADR-030 | CI runtime matrix and fault injection | P2 | Release confidence | Low | ADR-016 |
| ADR-031 | Docker image canonicalization for production-lite | P2 | Deploy reproducibility | Low | — |

## Acceptance bar (all proposed ADRs)

1. No change to frozen 14 runtime JSON artifact set without major version.
2. No new mandatory inspection CLI commands.
3. Runtime behavior changes must be **opt-in** via env/settings defaulting to v1.0.0 behavior.
4. Contract tests updated when additive CLI flags ship.

## Suggested review order

1. ADR-019 (acknowledge planning track)
2. ADR-020 → ADR-021 → ADR-022 (reliability cluster)
3. ADR-023 → ADR-024 (observability)
4. ADR-031 (Docker docs/image)
5. ADR-025 → ADR-026 → ADR-027 (scale path)
6. ADR-029, ADR-030, ADR-028 (parallel as needed)
