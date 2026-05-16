# Post-v1.0.0 operational hardening roadmap

**Status:** Planning only (no runtime behavior changes on this branch)  
**Audience:** Maintainers, operators, architecture reviewers  
**Freeze:** v1.0.0 contracts remain authoritative ([STABILITY_GUARANTEES.md](STABILITY_GUARANTEES.md), [architecture/RUNTIME_CONTRACTS.md](architecture/RUNTIME_CONTRACTS.md))

This document records production-readiness findings after burn-in ([BURN_IN_REPORT.md](BURN_IN_REPORT.md)) and proposes **opt-in** improvements for a future **v1.1+** line. Nothing here is implemented by default.

---

## Principles

| Rule | Meaning |
|------|---------|
| No frozen contract changes | 14 `runtime/*.json` names, lifecycle 1–14, 11 inspection CLIs, schema v1 |
| No breaking CLI changes | Additive flags only; deprecations require major version + ADR |
| Opt-in only | New metrics, storage, queues, schedulers behind settings/env |
| Evidence unchanged | Existing burn-in artifacts and drill fixtures stay valid |
| Plan before platform | Prefer operator runbooks and bounded code fixes over control planes |

**Backlog:** [POST_V1_TODO_BACKLOG.md](POST_V1_TODO_BACKLOG.md) · **ADR candidates:** [architecture/POST_V1_ADR_BACKLOG.md](architecture/POST_V1_ADR_BACKLOG.md) · **RFCs:** [rfc/](rfc/)

---

## 1. Technical debt

| ID | Area | Finding | Suggested direction (opt-in) |
|----|------|---------|------------------------------|
| TD-01 | Retry | Three implementations: `collector/retry.py`, `publisher/retry.py`, `workers/retry.py` | Shared `utils/retry_policy.py` with pluggable classifiers |
| TD-02 | Errors | `workers/retry.classify_exception` vs `utils/error_classifier.classify_runtime_error` | Single taxonomy; scheduler and workers use same module |
| TD-03 | Formatting | `publisher/formatting.py` vs `publisher/publish_formatting.py` overlap | One module; moderation imports publish helpers |
| TD-04 | Metrics | `publish_retries` defined in `utils/metrics.py` but never incremented in production publish path | Wire `inc("publish_retries")` in `publisher/telegram_publisher.py` or remove from benchmark/observability |
| TD-05 | Naming | `worker/` (transport) vs `workers/` (runtime) | Docs alias table only in v1.1; rename is major-version |
| TD-06 | OpenAI | `ai/cluster_summarizer.py` manual retry loop + SDK `max_retries` | Document effective retry budget; optional unified wrapper |
| TD-07 | Docker | Root `Dockerfile` vs `deploy/Dockerfile.example` vs Compose build context | Single documented “production-lite image” path in DEPLOYMENT_QUICKSTART |
| TD-08 | Intelligence | `editorial/intelligence_store.py` sync JSON under async pipeline | Async I/O or explicit “blocking section” in ops docs |
| TD-09 | Admin notify | `bot/handlers.py` direct `send_message` without publisher retry | Route through thin notify helper with bounded retry |
| TD-10 | Tests | Contract-heavy; live Telegram/OpenAI paths mostly mocked | Expand opt-in integration matrix (see RFC-009) |

---

## 2. Operational risks

| Risk | Likelihood | Impact | Mitigation (current) | Hardening (proposed) |
|------|------------|--------|----------------------|----------------------|
| Multi-process SQLite writers | Medium | DB corruption | WAL + single-writer docs | Process supervisor policy; optional Postgres |
| Ack-before-retry job loss | Low | Silent job drop | Logs `worker.ack_before_retry_failed` | Re-enqueue before ack or idempotent delivery IDs |
| Publish lock Redis fallback | Medium | Duplicate publish | Local lock only per process | Fail closed or queue-only publish mode |
| Partial multi-chunk Telegram post | Medium | Channel inconsistency | Operator manual cleanup | Chunk transaction journal or single-message cap |
| Live DB restore | Medium | Corruption | Operator stops app first | `backup_cli --require-quiesce` hook |
| Missing Telethon session in backup zip | High | Re-auth required | Not in `backup_cli` scope | Document + optional session path in backup |
| Nightly ops not in Compose | Medium | Stale inspection tree | systemd timer / host `make` | Document-only sidecar pattern (no new daemon) |
| Dead metrics in qualification | Low | False confidence | Cross-check logs | Fix counters or label “synthetic” in reports |
| Secrets in `.env` on disk | Medium | Leak | SECURITY.md | Optional secret backend RFC-008 |
| Operator skill gap | Medium | Mis-read WARNING vs FAIL | FAILURE_DRILLS, START_HERE | Hardening runbook cross-links |

---

## 3. Scalability limits (v1.0.0 baseline)

- **Single node:** One `RUNTIME_STATE_DIR`, one inspection `OUTPUT_DIR` context per nightly ([KNOWN_LIMITATIONS.md](KNOWN_LIMITATIONS.md)).
- **SQLite:** Suitable for low concurrent write rate; not a multi-tenant warehouse.
- **Scheduler + bot in `app/main.py`:** One asyncio process; workers are separate processes sharing DB/Redis without in-repo leader election.
- **Redis optional:** Queue/reliable transport scales horizontally only when Redis enabled and locks honored.
- **OpenAI:** Throughput bounded by model rate limits and serial cluster summarization patterns.
- **Frozen inspection:** 14 JSON artifacts sized for human review, not petabyte telemetry.

---

## 4. Reliability gaps

| Gap | Location | Notes |
|-----|----------|-------|
| Job loss on retry enqueue failure | `workers/runtime.py` (~366–374) | Ack then re-enqueue; enqueue failure after ack |
| No cross-process pipeline lock | `scheduler/pipeline_lock.py` | `asyncio.Lock` only |
| Healthcheck excludes Telegram/API | `docker/healthcheck.py` | Liveness ≠ credentials validity |
| FloodWait not modeled in publisher retry | `publisher/retry.py` | Fixed delay; Telethon collector has separate handling |
| DLQ visibility split | Redis DLQ vs in-process metrics | Ops HTTP `/ops/dlq` vs frozen JSON inspection |
| No automatic remediation | By design (ADR-003) | Operators run `make runtime-nightly` |

---

## 5. Observability improvements (opt-in proposals)

| Item | Current state | Proposal |
|------|---------------|----------|
| Structured metrics | In-process counters in `utils/metrics.py`; Prometheus via `/metrics` | RFC-001: namespaced counters/histograms, opt-in `METRICS_PROFILE=prometheus` |
| Redis transport | `utils/redis_transport_metrics.py` not in Prometheus export | RFC-001: merge snapshot in `export_snapshot()` behind flag |
| Runtime inspection | Strong offline model (`newsroom.cli`) | Keep frozen; link live `/metrics` from OPERATOR_QUICKSTART |
| Tracing | None | Out of scope unless OpenTelemetry opt-in module added |
| Log correlation | `log_event` helpers | Optional `delivery_id` on all worker log lines (additive) |

---

## 6. Backup / restore edge cases

| Scenario | Behavior today | Gap | Proposal |
|----------|----------------|-----|----------|
| SQLite backup | `tools/backup_cli.py backup-create` | Postgres URL unsupported | RFC-004: pg_dump path behind `DATABASE_URL` driver |
| Restore over live DB | File copy in place | WAL lock risk | Document stop order; optional `.backup_cli.lock` |
| Runtime snapshot | `scripts/runtime_snapshot.sh` | Not a DB substitute | Already documented in RESTORE_PROCEDURE |
| OUTPUT_DIR restore | `scripts/runtime_restore.sh` | Inspection tree only | Burn-in checklist item |
| Telethon `.session` | Not in zip | DR gap | Runbook section + optional `--include-session` |
| `.env` / secrets | Not in zip | Expected | Secrets management RFC-008 |
| `runtime_bundle.zip` | Nightly output | Missing → recovery WARNING | FAILURE_DRILLS `missing_bundle` |
| Cross-version restore | schema v1 JSON | Major bump needs compatibility report | ADR-009 additive fields only in 1.x |

---

## 7. Telegram / API failure scenarios

| Scenario | Handling | Hardening idea |
|----------|----------|----------------|
| Bot token invalid | Runtime failure on traffic; healthcheck silent | Optional `newsroom.cli health --live-probe` (new flag only) |
| FloodWait / rate limit | Collector retry; publisher fixed delay | Shared rate-limit aware backoff |
| Multi-part message partial failure | `telegram_publisher.py` chunks | All-or-nothing flag or rollback note in draft state |
| Telethon disconnect | `collector/retry.py`, reconnect counter | Expose `telethon_reconnects` in ops bundle |
| OpenAI 429/5xx | SDK + cluster_summarizer loops | Cap total attempts; surface in `openai_failures` |
| Admin notification failure | `admin_notify_failures` metric | Retry wrapper in bot layer |
| Channel permission loss | Publish failure metrics | Draft stuck state runbook |

---

## 8. SQLite concurrency limitations

- **PRAGMAs:** WAL enabled in `db/session.py` — improves concurrent readers; still one writer.
- **Second SQLite:** Telethon `SQLiteSession` session file — second writer if same disk contention.
- **Workers + app:** Multiple processes = operator responsibility ([KNOWN_LIMITATIONS.md](KNOWN_LIMITATIONS.md)).
- **Migration candidate:** PostgreSQL already referenced in `deploy/docker-compose.postgres.yml` and `tests/test_postgres_compat.py` — not production-lite default.

---

## 9. Docker operational concerns

| Topic | Finding |
|-------|---------|
| Image drift | Compose uses `deploy/Dockerfile.example`; root `Dockerfile` differs (user, COPY scope, HEALTHCHECK) |
| Volumes | `newsroom_data` + `newsroom_runtime` split vs mental model of single `/data` tree |
| Nightly | No Compose service; use host systemd `deploy/systemd/newsroom-nightly.*` |
| Bootstrap | `deploy/bootstrap.sh` creates dirs only — no migrate/backup/verify |
| Non-root | Root Dockerfile uses `appuser`; example Dockerfile may differ — document which is canonical |
| Inspection CLI in image | Slim runtime image may omit dev paths; `pip install -e .` assumed |

---

## 10. Future migration candidates

| Candidate | From | To | Risk | Notes |
|-----------|------|-----|------|-------|
| Database | SQLite file | PostgreSQL | High | Alembic/migrations exist; dual-write period needed |
| Queue | In-memory / optional Redis | Pluggable backend | Medium | RFC-003 |
| Scheduler | APScheduler in-process | Distributed cron | High | Conflicts with ADR-003 unless external only |
| Storage | Local JSON intelligence | Pluggable object store | Medium | RFC-004 |
| Metrics | In-process | OTLP/Prometheus agent | Low | Opt-in sidecar |
| Deployment | Compose + systemd | K8s | Out of repo scope | FAQ defers to external |

---

## 11. Code audit summary

### 11.1 Duplicated logic

- Retry: `collector/retry.py`, `publisher/retry.py`, `workers/retry.py`
- Error classification: `workers/retry.py` vs `utils/error_classifier.py`
- Telegram HTML: `publisher/formatting.py` vs `publisher/publish_formatting.py`

### 11.2 Fragile retry / backoff

- `publisher/retry.async_retry`: fixed delay, retries `BaseException`
- `workers/runtime.py`: ack-before-retry ordering
- `ai/cluster_summarizer.py`: nested retry without global deadline
- `utils/redis_resilience.py` vs `worker/reliable_transport.py`: stacked reconnect loops

### 11.3 Potential race conditions

- `publisher/publish_lock.py`: Redis failure → local lock, still yields acquired
- `scheduler/pipeline_lock.py`: process-local only
- `editorial/intelligence_store.py`: `threading.RLock` + sync I/O in async context
- `workers/state.py`: per-process counters; watchdog merge via Redis heartbeat only

### 11.4 Implicit assumptions

- Single writer for SQLite newsroom DB
- Redis available ⇒ distributed lock works
- `publish_service.py` is sole publish path (bot admin paths bypass)
- `OUTPUT_DIR` regenerated by nightly, not mutated by inspection CLIs
- DRY_RUN skips external side effects but still exercises much of pipeline

### 11.5 Weak module boundaries

- `app/main.py` couples scheduler, bot, transport init
- `observability/` frozen vs `tools/admin_cli.py` live ops surface
- `worker/` vs `workers/` package split

### 11.6 Under-covered integration paths

| Path | Test signal | Gap |
|------|-------------|-----|
| Full publish with Redis lock | Partial mocks | Multi-worker integration |
| backup-create → restore → verify | Unit-level | No CI restore drill |
| Postgres compose stack | `test_postgres_compat.py` | Not in default `ci-test` |
| Telethon live collect | Mocked in most tests | Optional nightly live job |
| runtime-nightly → all 12 required JSON | smoke/contracts | Host env dependent |
| Worker ack/retry failure | `test_worker_runtime.py` | Enqueue-after-ack failure path |

---

## 12. RFC-style proposals (not implemented)

Detailed drafts live under [rfc/](rfc/). Summary:

| RFC | Title | Opt-in surface |
|-----|-------|----------------|
| [RFC-001](rfc/RFC-001-structured-metrics.md) | Structured metrics and Prometheus alignment | `METRICS_EXPORT=extended` |
| [RFC-002](rfc/RFC-002-health-endpoints.md) | Deep health vs liveness | `HEALTH_PROFILE=deep` |
| [RFC-003](rfc/RFC-003-queue-abstraction.md) | Queue backend interface | `QUEUE_BACKEND=redis\|memory` |
| [RFC-004](rfc/RFC-004-pluggable-storage.md) | Storage drivers (DB + intelligence) | `STORAGE_PROFILE=postgres` |
| [RFC-005](rfc/RFC-005-postgresql-migration.md) | PostgreSQL migration path | `DATABASE_URL` + migration gate |
| [RFC-006](rfc/RFC-006-distributed-scheduling.md) | External scheduling only | systemd/K8s CronJob docs |
| [RFC-007](rfc/RFC-007-multi-channel-publishing.md) | Multi-channel publish | `TARGET_CHANNELS` list |
| [RFC-008](rfc/RFC-008-secrets-management.md) | Secrets backends | `SECRETS_PROVIDER=env\|file\|vault` |
| [RFC-009](rfc/RFC-009-ci-runtime-matrix.md) | CI matrix (py × redis × db) | GitHub Actions only |
| [RFC-010](rfc/RFC-010-chaos-fault-injection.md) | Fault injection harness | `NEWSROOM_CHAOS=1` test-only |

---

## 13. Prioritized roadmap

### P1 — High operational impact, bounded scope

| Item | Impact | Migration risk | Est. effort |
|------|--------|----------------|-------------|
| Fix ack-before-retry semantics | Prevents rare job loss | Low — behavior fix behind flag | 1–2 d |
| Publish lock fail-closed mode | Prevents duplicate publish | Low — `PUBLISH_LOCK_STRICT=1` | 1 d |
| Wire or remove dead `publish_retries` metric | Restores signal trust | None | <1 d |
| Backup restore quiesce documentation + CLI guard | Safer DR | Low — opt-in `--stop-hint` | 1 d |
| Unify error classifier | Consistent retry policy | Low | 2 d |
| Telethon session backup runbook | Faster recovery | None (docs) | <1 d |

### P2 — Medium impact, v1.1 theme

| Item | Impact | Migration risk | Est. effort |
|------|--------|----------------|-------------|
| RFC-001 metrics alignment | Better ops | Low | 3–5 d |
| RFC-002 deep health (opt-in) | Faster incident detection | Low | 2–3 d |
| Retry policy module | Less drift | Medium | 3–5 d |
| Integration: backup round-trip test | CI confidence | Low | 2 d |
| Docker image path consolidation (docs + one Dockerfile) | Fewer deploy mistakes | Low | 2 d |

### P3 — Strategic / higher risk

| Item | Impact | Migration risk | Est. effort |
|------|--------|----------------|-------------|
| RFC-005 PostgreSQL default path | Scale writes | High | weeks |
| RFC-006 distributed scheduling (external) | HA operations | Medium (ops) | docs + weeks |
| RFC-007 multi-channel | Product expansion | Medium | weeks |
| RFC-010 chaos harness | Reliability culture | Low in CI only | 1–2 w |
| Package rename `worker`/`workers` | Clarity | High (imports) | major version |

---

## 14. Architecture decision backlog

See [architecture/POST_V1_ADR_BACKLOG.md](architecture/POST_V1_ADR_BACKLOG.md). Proposed ADR-019+ remain **Proposed** until accepted with implementation plan.

Planning record: [architecture/ADR-019-post-v1-hardening-roadmap-planning-only.md](architecture/ADR-019-post-v1-hardening-roadmap-planning-only.md).

---

## 15. What we explicitly will not do in v1.0.x

- Add runtime JSON artifacts or inspection CLI commands
- Mandate Kubernetes, Prometheus, Grafana, Celery
- Auto-heal production state from inspection tools
- Breaking changes to Makefile targets or tri-state enums

---

## Related

- [MAINTENANCE_MODE.md](MAINTENANCE_MODE.md) · [KNOWN_LIMITATIONS.md](KNOWN_LIMITATIONS.md)
- [BURN_IN_REPORT.md](BURN_IN_REPORT.md) · [FAILURE_DRILLS.md](FAILURE_DRILLS.md)
- [RESTORE_PROCEDURE.md](RESTORE_PROCEDURE.md) · [OPERATIONAL_CONFIDENCE.md](OPERATIONAL_CONFIDENCE.md)
