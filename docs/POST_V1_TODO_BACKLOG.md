# Post-v1 TODO backlog

Actionable items for **v1.1+** planning. Not scheduled for v1.0.x unless marked as doc-only. Link: [post_v1_hardening.md](post_v1_hardening.md).

**Legend:** `[ ]` open · `[~]` in design (RFC/ADR) · `[x]` done · `W` won't fix in scope

---

## P1 — Reliability and operator trust

- [ ] **P1-01** Fix worker ack-before-retry ordering (`workers/runtime.py`) — re-enqueue before ack or transactional outbox (opt-in `WORKER_RETRY_SAFE=1`)
- [ ] **P1-02** Add `PUBLISH_LOCK_STRICT=1` fail-closed when Redis lock unavailable (`publisher/publish_lock.py`)
- [ ] **P1-03** Wire `inc("publish_retries")` in `publisher/telegram_publisher.py` OR remove from benchmark/observability exports
- [ ] **P1-04** Merge `redis_transport_metrics` into Prometheus export behind `METRICS_EXPORT=extended`
- [ ] **P1-05** Unify `workers/retry.classify_exception` and `utils/error_classifier` (single module)
- [~] **P1-06** Document backup restore stop order + optional `backup_cli --dry-run` restore validation
- [ ] **P1-07** Add Telethon session path to [RESTORE_PROCEDURE.md](RESTORE_PROCEDURE.md) disaster checklist

## P2 — Observability and integration

- [~] **P2-01** Implement RFC-001 structured metrics (opt-in)
- [~] **P2-02** Implement RFC-002 deep health profile (opt-in)
- [ ] **P2-03** CI test: backup zip round-trip on temp SQLite (no live Telegram)
- [ ] **P2-04** Consolidate Docker production-lite image documentation (single canonical Dockerfile)
- [ ] **P2-05** Admin notify bounded retry helper (`bot/handlers.py`)
- [ ] **P2-06** Shared retry policy module; deprecate duplicate retry files gradually

## P3 — Scale and platform (major / opt-in)

- [~] **P3-01** RFC-005 PostgreSQL migration design review
- [~] **P3-02** RFC-003 queue abstraction spike
- [~] **P3-03** RFC-007 multi-channel publishing design
- [W] **P3-04** In-repo Kubernetes manifests — external per FAQ
- [~] **P3-05** RFC-010 chaos harness for CI only
- [~] **P3-06** RFC-008 secrets provider interface

## Documentation (safe anytime)

- [x] **DOC-01** `docs/post_v1_hardening.md` audit and roadmap
- [x] **DOC-02** `docs/POST_V1_TODO_BACKLOG.md` (this file)
- [x] **DOC-03** `docs/architecture/POST_V1_ADR_BACKLOG.md`
- [x] **DOC-04** RFC drafts under `docs/rfc/`
- [ ] **DOC-05** Link hardening roadmap from operator burn-in closeout template

## Contract / freeze guards

- [x] **CG-01** Contract test: post-v1 docs exist; no “mandatory new runtime artifact” language
- [ ] **CG-02** Any P1 code change requires contract test update only if additive CLI flags documented
