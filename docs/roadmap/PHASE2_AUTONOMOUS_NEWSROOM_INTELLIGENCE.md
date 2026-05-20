# Phase 2 — Autonomous newsroom intelligence

**Status:** roadmap (post `v3.0.0-production-runtime-baseline`)  
**Baseline:** production-grade runtime on Timeweb VPS (`v3-live-telegram-validation` → `main`, tag `v3.0.0-production-runtime-baseline`)

## Goal

Evolve from **stable operational runtime** to **autonomous editorial intelligence** without compromising fail-open production behavior.

## Workstreams

### 1. Quality scoring (Phase 2.1 — shipped on `feature/phase2-quality-scoring`)

- Explainable `editorial_scores` + `draft_extras.editorial_intelligence` (contract: `editorial/scoring/CONTRACT.md`)
- Per-draft signals persisted; operator preview in Telegram

### 2. Source trust evolution (Phase 2.2 — recommended next)

- Dynamic source reputation beyond static JSON
- Historical accuracy, operator corrections, cluster reliability
- Source decay/recovery on existing scoring substrate

### 3. Editorial memory (Phase 2.3+)

- Per-draft / per-cluster quality signals persisted and exposed on `/health` v2 extensions
- Gate publish decisions on configurable thresholds (profile-aware)
- Operator-visible quality breakdown in admin Telegram + dashboard

### 4. Editorial memory (continued)

- Long-horizon context: topics, entities, recurring narratives, channel voice
- Memory retrieval in summarization / headline / safety passes
- Retention policy aligned with `runtime_ops` and SQLite/Postgres backends

### 3. Adaptive prioritization

- Source and cluster priority from engagement, freshness, conflict density, pipeline backlog
- Scheduler tick budget allocation (collect → cluster → draft → publish)
- Degraded-mode aware: skip AI-heavy stages when OpenAI/Telethon unavailable

### 5. Semantic dedup evolution

- Move beyond lexical Jaccard: embedding-backed near-duplicate detection (optional, feature-flagged)
- Cross-channel duplicate suppression with explainable skip reasons in metrics
- Backward-compatible fallback to current lexical pipeline

### 6. Operator analytics layer

- **Follow-up (separate PR):** fix `runtime_ops_state` persistence — atomic writes for
  `consecutive_failures`, `last_degraded_reason`, recovery timestamps, dependency transitions
- SLO dashboards from Prometheus + structured logs
- Incident bundle enrichment (`tools/debug_telegram_runtime.sh`)

## Non-goals (Phase 2)

- Kubernetes / workflow orchestration (ADR-003)
- Mandatory AI on startup (remain fail-open degraded)
- Replacing Telegram polling supervisor

## Acceptance (Phase 2 exit)

- [ ] Quality score visible per published post; configurable publish gate
- [ ] Editorial memory influences ≥1 pipeline stage with measurable latency budget
- [ ] Prioritization changes source order under load without starvation
- [ ] Semantic dedup reduces duplicate publishes in soak test (metric: `skipped_duplicates`)
- [ ] `runtime_ops_state` rows reflect live transitions after restart

## Suggested GitHub issue title

**Phase 2 — Autonomous newsroom intelligence**

Copy this file into the issue body or link: `docs/roadmap/PHASE2_AUTONOMOUS_NEWSROOM_INTELLIGENCE.md`
