# Launch readiness report (template)

Generated during final staging. Fill after running checklist and smoke tests.

## System snapshot

```bash
curl -s http://127.0.0.1:8080/health | python3 -m json.tool
```

Record:

| Field | Value |
|-------|--------|
| `status` | |
| `staging.launch_ready` | |
| `staging.publishing.published_1h` | |
| `staging.publishing.drafts_pending` | |
| `staging.pipeline.starvation_active` | |
| Critical alerts | |

## Migration notes (this release)

- **`/health`** now includes top-level **`staging`** block (pipeline, editorial, publishing, alerts).
- New env keys (optional): `DESK_CATEGORY_*_MIN`, `STAGING_ZERO_DRAFT_TICKS`, `STAGING_PUBLISH_FAILURES_1H_WARN`, `STAGING_TICK_LOOKBACK`.
- **`desk.decision`** logs include **`reason_code`** (e.g. `desk.market.below_priority_threshold`).
- **`publish.trace`** structured events on publish start/success/failure.
- No DB schema migration required for staging observability (uses existing `pipeline_ticks`, `failed_drafts`, `published_posts`).

## Known risks

| Risk | Mitigation |
|------|------------|
| OpenAI quota exhausted | Starvation fallback summarizer; monitor `openai.generation_degraded` alert |
| Dual runtime (VPS + Mac) | Single worker per `BOT_TOKEN`; flock lock + stop remote service |
| First publish never attempted | Manual `/publish` or admin approve after media fix deployed |
| Collect lag | `PIPELINE_INTERVAL_MINUTES`, source health runbook |

## GO / NO-GO verdict (2026-05-24)

| Criterion | Status |
|-----------|--------|
| Transport layer (`telegram_transport.py`) in repo | **DONE** |
| Singleton lock on startup (`enforce_singleton_or_exit`) | **DONE** |
| Handler error boundary (`SafeHandlerMiddleware` + `dp.errors`) | **DONE** |
| `/health` → `staging` (pipeline, publishing, runtime, alerts) | **DONE** |
| New code running in production process | **OPERATOR** — run `bash scripts/restart_newsroom_clean.sh` |
| ≥1 media publish after restart | **OPERATOR** |
| 3 consecutive collect→publish cycles | **OPERATOR** |
| No duplicate `app.main` / VPS+Mac same token | **OPERATOR** |

**Verdict: NO-GO** for public channel until:

1. Clean restart with **only one** runtime (`pgrep -fl app.main` empty before start).
2. `/health` shows `staging.transport_layer_ok: true` and no `publishing.legacy_transport_kwargs` alert.
3. Failed draft retry succeeds: `failed` → `pending` → `published`.
4. Admin bot responds to `/health` or draft commands within 5s.

**GO** when [FINAL_STAGING_CHECKLIST.md](runbooks/production/FINAL_STAGING_CHECKLIST.md) is signed off and above four items are verified on the target channel.
