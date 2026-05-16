# ADR-002: Static operational dashboard

Status: Accepted  
Date: 2026-05-15

Scope: `utils/operational_dashboard.py`, `tools/build_operational_dashboard.py`, HTML artifacts.

## Context

Operators need a **single glanceable** view of bundle, regression, qualification, and optional retention JSON after an incident or CI run. A live React/SPA observability UI would add build tooling, auth surface, and moving parts misaligned with a **single-node** deployment story.

## Decision

Ship a **static HTML** dashboard generator:

- Inputs are **files** (zip + JSON), not live sockets.
- Output is one **self-contained** HTML file suitable for attachment or static hosting.
- Regeneration is **deterministic** given the same inputs (no server-side rendering, no external chart SaaS).

## Consequences

- **Positive:** Zero dashboard runtime dependency; works air-gapped; trivial to archive next to `runtime_bundle.zip`.
- **Negative:** No realtime drill-down; refresh requires re-running the tool with fresh inputs.

## Non-goals

- No mandated Grafana/Datadog/New Relic integration.
- No websocket live tail of logs inside the dashboard artifact.
