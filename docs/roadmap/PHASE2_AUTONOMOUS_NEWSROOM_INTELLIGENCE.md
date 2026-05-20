# Phase 2 — Autonomous newsroom intelligence

**Status:** roadmap (post `v3.0.0-production-runtime-baseline`)  
**Baseline:** production-grade runtime on Timeweb VPS (`main`, tag `v3.0.0-production-runtime-baseline`)

## Goal

Evolve from **stable operational runtime** to **autonomous editorial intelligence** without compromising fail-open production behavior.

## Workstreams

### 1. Quality scoring (Phase 2.1 — `feature/phase2-quality-scoring`)

- Explainable `editorial_scores` + `draft_extras.editorial_intelligence`
- Contract: `editorial/scoring/CONTRACT.md` (`phase2.1-v1`, scores `0.0..1.0`, `reason_codes`)
- Operator preview in Telegram; fail-open enrichment

### 2. Source trust evolution (Phase 2.2 — recommended next)

- Dynamic source reputation beyond static JSON
- Historical accuracy, operator corrections, cluster reliability
- Source decay/recovery on scoring substrate

### 3. Editorial memory

- Long-horizon context: topics, entities, recurring narratives, channel voice
- Memory retrieval in summarization / headline / safety passes

### 4. Adaptive prioritization

- Source and cluster priority from engagement, freshness, conflict density, pipeline backlog
- Scheduler tick budget allocation (collect → cluster → draft → publish)

### 5. Semantic dedup evolution

- Embedding-backed near-duplicate detection (feature-flagged)
- Explainable skip reasons in metrics

### 6. Operator analytics layer

- Fix `runtime_ops_state` persistence (separate ops PR)
- SLO dashboards from Prometheus + structured logs

## Non-goals (Phase 2)

- Kubernetes / workflow orchestration (ADR-003)
- Mandatory AI on startup (remain fail-open degraded)
- RLHF / autonomous publishing / self-modifying ranking

## Deploy note (Phase 2.1)

```bash
alembic upgrade head   # mandatory before app start
```

## Suggested GitHub issues

- **Phase 2.2 — Source trust evolution**
- **Phase 2 — Autonomous newsroom intelligence** (umbrella)
