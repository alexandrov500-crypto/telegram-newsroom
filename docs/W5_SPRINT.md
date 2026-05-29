# W5 Implementation Sprint — Monetization + Network Capitalization

Transition: media network → monetizable autonomous intelligence media company.

---

## 1. W5 Architecture Redesign

```mermaid
flowchart TB
  subgraph editorial [Editorial W3]
    ENR[enrich_for_publish]
    ID[identity_engine]
  end
  subgraph w5 [W5 Monetization]
    REV[revenue_engine]
    SP[sponsor_injection]
    PR[premium_layer]
    AV[audience_value]
    AD[ad_inventory]
    BAL[monetization_balance]
    FUN[conversion_funnel]
    PKG[asset_packaging]
    FF[financial_feedback]
    API[b2b_feed + api_handlers]
  end
  subgraph surfaces [Revenue Surfaces]
    MAIN[Telegram main]
    PREM[premium channel]
    RSS[RSS /feed.xml]
    B2B[/api/v1/*]
  end
  ENR --> REV
  REV --> SP
  REV --> PR
  REV --> FUN
  SP --> BAL
  AD --> SP
  AV --> FUN
  MAIN --> FF
  FF --> CAD[cadence_engine ROI boost]
  FF --> AP[audience_prioritizer LTV]
  MAIN --> API
  PR --> PREM
  PKG --> RSS
```

**Hot path:** draft approved → `enrich_with_monetization()` → Telegram send → `record_revenue_event()` → financial feedback cache

**Maintenance (12h):** profitability refresh, sponsor cap reset, audience LTV map

---

## 2. Monetization System Design

| Stream | Trigger | Surface |
|--------|---------|---------|
| ORGANIC | default | main channel |
| SPONSORED | eligibility≥0.52, safety≥0.62, ad slot free | main + partner block |
| PREMIUM | insight≥0.72, style≥0.65 | free preview main + full premium channel |
| B2B_API | insight≥0.68 | `/api/v1/feed` |
| SYNDICATION | insight≥0.68 | RSS `/feed.xml` |
| DATA_LICENSE | macro/finance/crypto + score≥0.6 | revenue attribution |

**Eligibility formula:**
```
score = 0.25·signal + 0.25·insight + 0.20·style
sponsor_safe = style≥0.58 AND insight≥0.45 AND NOT breaking
premium = insight≥0.72 AND len≥320
syndication = insight≥0.68 AND style≥0.62
```

---

## 3. Sponsor Injection Pipeline

```
content → score_sponsor_safety (block war/tragedy/sanctions context)
       → evaluate_monetization_stress (sponsor_ratio_24h ≤ 18%)
       → allocate_ad_slot (CTR proxy ≥ 0.015, daily_cap ≤ 2)
       → pick_sponsor_slot (DB or env default)
       → inject_sponsor_block ("— партнёрский материал")
       → record_sponsor_use + record_publish_type("sponsored")
```

**Safety score:** base 0.7 − forbidden context − existing marker − short text

---

## 4. Premium Layer Architecture

- `classify_premium_content()` — tiers: standard | premium | intel
- Free channel: preview (280 chars) + gate message
- Premium channel: full body via `TELEGRAM_PREMIUM_CHANNEL_ID`
- Audit: `premium_content_log` table

---

## 5. API Productization Schema

| Endpoint | Schema | Auth |
|----------|--------|------|
| `GET /api/v1/feed` | `newsroom.feed.v1` | `X-Api-Key` |
| `GET /api/v1/narratives` | `newsroom.narratives.v1` | optional if key unset |
| `GET /api/v1/signals` | `newsroom.signals.v1` | optional |
| `GET /api/v1/sources/reliability` | `newsroom.sources.v1` | optional |
| `GET /feed.xml` | RSS 2.0 | public |
| `GET /export/rss` | RSS 2.0 alias | public |

Rate limit: `W5_B2B_API_RATE_LIMIT_HOUR` (default 120) per API key.

---

## 6. Audience Value Scoring Model

```
ltv = 0.35 + affinity×0.45 + momentum×0.20
elasticity = 0.4 + affinity×0.35
churn_risk = max(0.05, 0.55 − affinity×0.4 − momentum×0.15)
conversion_prob = min(0.85, 0.12 + affinity×0.35 + elasticity×0.15)
```

**Ranking integration:** `audience_prioritizer` × `(0.92 + ltv×0.12)`

---

## 7. Ad Optimization Engine

**CTR proxy (rule-based):**
```
base = 0.018
+ 0.006 if macro/crypto/finance
+ 0.004 if narrative peak/breaking
+ 0.005 if hour 8–11 or 17–20
+ (mood − 0.5)×0.01
```

Allocate if `ctr ≥ W5_AD_MIN_PREDICTED_CTR` (0.015) and under daily cap.

---

## 8. Conversion Funnel System

| Stage | CTA trigger |
|-------|-------------|
| premium | conversion_prob ≥ 0.45 |
| retention | churn_risk ≥ 0.4 |
| engagement | ltv ≥ 0.55 |
| awareness | default |

Events logged to `conversion_events` (aggregate, no PII).

---

## 9. Editorial Monetization Guardrails

- `W5_MAX_SPONSOR_RATIO_24H=0.18` — blocks new sponsor injection, NOT editorial publishes
- `score_sponsor_safety` — blocks unsafe contexts
- Identity gate (W3) still applies before monetization enrich
- Floor publish (`PUBLISH_FLOOR_ENABLED`) bypasses monetization blocks

---

## 10. Revenue Feedback Loop

```
revenue_events → refresh_topic_profitability() → topic_profitability_memory
              → topic_roi_cache.json (sync read)
              → cadence_engine: roi_boost > 1.08 → min_interval × 0.92
              → audience_prioritizer: LTV multiplier
```

**Profitability boost:** `clamp(0.88, 1.15, 0.95 + roi×0.02)`

---

## 11. DB Schemas

```sql
revenue_events(id, draft_id, stream, surface, amount_usd, topic_bucket,
               eligibility_score, extras_json, created_at)

sponsor_slots(id, slot_key, sponsor_name, verticals_json, copy_template,
              cpm_usd, daily_cap, used_today, active, updated_at)

conversion_events(id, event_type, funnel_stage, cohort, draft_id,
                    value_score, extras_json, created_at)

topic_profitability_memory(id, topic_bucket, revenue_sum, engagement_sum,
                           roi_score, sample_count, updated_at)

premium_content_log(id, draft_id, tier, insight_score, free_preview_hash,
                    premium_channel_id, published_at, created_at)
```

---

## 12. API Specs (examples)

**Feed item:**
```json
{
  "id": "draft:42",
  "title": "ФРС сигнализирует...",
  "summary": "...",
  "published_at": "2026-05-30T12:00:00+00:00",
  "telegram_post_id": 89
}
```

**Signal item:**
```json
{
  "draft_id": 42,
  "engagement_score": 0.62,
  "virality_score": 0.41,
  "topic_bucket": "macro",
  "impact_proxy": 0.54
}
```

---

## 13. Scheduling System

| Job | Interval | Module |
|-----|----------|--------|
| monetization_maintenance | 12h | profitability + sponsor reset + LTV map |

Env: `W5_MONETIZATION_MAINTENANCE_ENABLED`, `W5_MONETIZATION_MAINTENANCE_INTERVAL_HOURS`

---

## 14. Failure Modes

| Failure | Mitigation |
|---------|------------|
| Sponsor overload | auto-block injection; editorial continues |
| Premium channel misconfig | log skip; main preview still publishes |
| B2B API key leak | rotate `W5_B2B_API_KEY`; rate limit |
| Revenue DB write fail | non-blocking post-hook |
| ROI cache stale | maintenance job every 12h |

---

## 15. Rollback Strategy

```bash
W5_MONETIZATION_ENABLED=false          # disable all W5 enrich
W5_SPONSOR_INJECTION_ENABLED=false     # keep revenue tracking only
W5_B2B_API_ENABLED=false               # disable API routes
W5_RSS_FEED_ENABLED=false              # disable public RSS
```

W3 identity + W2 cadence + floor unaffected.

---

## 16. KPI System

| KPI | Source | Target D60 |
|-----|--------|------------|
| Sponsor ratio 24h | monetization_publish_log | ≤18% |
| Revenue events/day | revenue_events | track baseline |
| Premium conversion proxy | conversion_events | ↑ week-over-week |
| B2B API requests/h | rate limit state | within cap |
| Topic ROI spread | topic_profitability_memory | macro/crypto top quartile |
| Ad CTR proxy | ad_inventory_state | ≥0.02 avg |

---

## 17. Observability Metrics

**Logs:**
- `publish.w5_enrich_skipped`
- `publish.w5_revenue_recorded`
- `monetization.profitability_refreshed`
- `monetization.maintenance_complete`

**Counters:** extend with `monetization_sponsor_injected_total` (future)

---

## 18. Cost/Revenue Assumptions

| Item | Assumption |
|------|------------|
| Sponsor CPM | $12 default (env tunable) |
| Premium CPM | $45 equivalent |
| B2B API | $8 CPM equivalent attribution |
| Marginal compute | ~$0 (rule-based) |
| RSS/API bandwidth | negligible at <10k req/day |

Break-even: ~2 sponsor slots/day at 5k views ≈ $120/mo gross (illustrative).

---

## 19. Deployment Priorities

1. Deploy with `W5_MONETIZATION_ENABLED=true`, sponsors OFF (`W5_SPONSOR_INJECTION_ENABLED=false`)
2. Enable revenue tracking 48h — baseline eligibility scores
3. Enable RSS (`/feed.xml`) for syndication test
4. Set `W5_B2B_API_KEY` — enable `/api/v1/*`
5. Configure `TELEGRAM_PREMIUM_CHANNEL_ID` when premium channel ready
6. Add sponsor rows to `sponsor_slots` or env defaults
7. Enable sponsor injection after 18% ratio guard validated

---

## 20. What to Build First

1. Revenue engine + event logging (data before ads)
2. Financial feedback → cadence ROI boost
3. RSS feed (zero-risk external surface)
4. B2B API with auth + rate limit
5. Sponsor injection (last — highest brand risk)

---

## 21. What Breaks System If Wrong

1. **Sponsor ratio too high** — audience churn, identity erosion
2. **Premium paywall on all content** — main channel dies
3. **API without rate limit** — scrape cost + content theft
4. **Unsafe sponsor contexts** — brand/legal damage
5. **ROI feedback too aggressive** — editorial becomes ad-optimized spam

---

## 22. Production Risks

| Risk | Severity | Control |
|------|----------|---------|
| Monetization before identity stable | HIGH | W3 gate first |
| Public RSS scraping | MED | rate limit at CDN/nginx layer |
| Premium content duplication | MED | free_preview_hash dedupe |
| SQLite revenue writes | LOW | async session_scope |
| Empty sponsor_slots table | LOW | env default fallback |

---

## Module Tree

```
app/monetization/
  revenue_engine.py
  sponsor_injection.py
  premium_layer.py
  audience_value.py
  ad_inventory.py
  monetization_balance.py
  conversion_funnel.py
  asset_packaging.py
  financial_feedback.py
  b2b_feed.py
  pipeline.py
  api_handlers.py
  scheduler_jobs.py
```

## Test Plan

```bash
python3 -m pytest tests/test_monetization_w5.py tests/test_flywheel_w3.py tests/test_growth_w2.py -q
```

## Env Reference

See `deploy/timeweb/.env.example` W5 section.
