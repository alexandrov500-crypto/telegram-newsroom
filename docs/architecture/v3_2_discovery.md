# v3.2 architecture discovery

**Design-only document.** No runtime changes, no schema migrations, no production branch experiments. Informs roadmap after [v3_2_planning_gate.md](../releases/v3_2_planning_gate.md).

## Discovery principles

- Preserve v3.1 publish semantics, retry model, and frozen `runtime/*.json` until explicit ADR + major gate
- Prefer operator-visible improvements over invisible automation
- Measure pain from [72h_operational_findings.md](../operations/72h_operational_findings.md) and [technical_debt_registry.md](technical_debt_registry.md)

---

## 1. Event bus abstraction

| | |
|--|--|
| **Problem** | Cross-component signals (publish ok, draft failed, cadence block) scattered in logs + timeline JSON |
| **Current limitation** | No unified internal event stream; coupling via DB status + ad hoc `append_timeline_event` |
| **Proposed direction** | Lightweight in-process event journal (file or SQLite table) with stable event types — not Kafka |
| **Operational risk** | Medium — duplicate handlers, ordering |
| **Migration complexity** | Medium — dual-write period |
| **Status** | **Exploratory** — not committed for v3.2 |

---

## 2. Publish queue introspection

| | |
|--|--|
| **Problem** | Operators cannot see pending publish jobs vs draft state in one view |
| **Current limitation** | Redis queue + DB status; CLI fragmentation |
| **Proposed direction** | Read-only `tools/publish_queue_inspect.py` (no Telegram writes) |
| **Operational risk** | Low if read-only |
| **Migration complexity** | Low |
| **Status** | **Candidate** for v3.2 ops tooling (docs + tool only phase) |

---

## 3. Moderation UI / API

| | |
|--|--|
| **Problem** | Bot-only moderation limits throughput and auditability |
| **Current limitation** | aiogram admin flows; no external moderation API |
| **Proposed direction** | Optional read-only HTTP dashboard for draft queue; writes still via bot or explicit API behind auth |
| **Operational risk** | High — auth, CSRF, duplicate actions |
| **Migration complexity** | High |
| **Status** | **Deferred** — requires ADR; not v3.2 default |

---

## 4. Multi-tenant isolation

| | |
|--|--|
| **Problem** | Single newsroom per deployment assumed |
| **Current limitation** | One `TARGET_CHANNEL_ID`, one policy bundle |
| **Proposed direction** | None for v3.2 — document unsupported |
| **Operational risk** | Critical if attempted ad hoc |
| **Migration complexity** | Very high |
| **Status** | **NOT planned** — out of scope ([unsupported_deployments.md](../scalability/unsupported_deployments.md)) |

---

## 5. Audit / event sourcing

| | |
|--|--|
| **Problem** | Full forensic replay of editorial decisions not available |
| **Current limitation** | Timeline events + DB state; no immutable audit log |
| **Proposed direction** | Append-only audit file per day (redacted), aligned with existing timeline |
| **Operational risk** | Low-Medium — PII in logs |
| **Migration complexity** | Medium |
| **Status** | **Exploratory** — compliance-driven tenants only |

---

## 6. Observability expansion

| | |
|--|--|
| **Problem** | Metrics are in-process; lost on restart |
| **Current limitation** | `utils/metrics.py` counters; diagnostics CLI |
| **Proposed direction** | Export snapshots to `var/ops_history/` on schedule (file-based, no new server) |
| **Operational risk** | Low |
| **Migration complexity** | Low |
| **Status** | **Candidate** — aligns with v1.9 intelligence patterns |

---

## 7. OpenTelemetry bridge

| | |
|--|--|
| **Problem** | Teams want traces in Jaeger/Tempo |
| **Current limitation** | Structured logs only; no OTel SDK |
| **Proposed direction** | Opt-in OTel exporter behind `OTEL_ENABLED=0` default |
| **Operational risk** | Medium — cardinality, PII in spans |
| **Migration complexity** | Medium |
| **Status** | **Deferred** — not mandatory for production-lite |

---

## 8. Prometheus metrics export

| | |
|--|--|
| **Problem** | No scrape endpoint for Grafana |
| **Current limitation** | Explicit non-goal in ENGINEERING_PHILOSOPHY |
| **Proposed direction** | Optional `tools/metrics_exporter.py` HTTP :9091 read-only gauge dump |
| **Operational risk** | Low if read-only + bound cardinality |
| **Migration complexity** | Low-Medium |
| **Status** | **Candidate** — opt-in only; ADR required before default-on |

---

## 9. Distributed scheduler safety

| | |
|--|--|
| **Problem** | Two schedulers could double-tick |
| **Current limitation** | Single-node assumption; no leader election |
| **Proposed direction** | Document + optional Redis leader lock for scheduler only |
| **Operational risk** | High if misconfigured |
| **Migration complexity** | Medium |
| **Status** | **NOT planned** for v3.2 — T2 still prefers single scheduler |

---

## 10. Replay / recovery tooling

| | |
|--|--|
| **Problem** | Recovery from partial failure requires tribal knowledge |
| **Current limitation** | Runbooks + manual DB/channel reconcile |
| **Proposed direction** | `tools/publish_reconcile.py` read-only diff: DB published vs channel (no auto-fix) |
| **Operational risk** | Low read-only; Medium if auto-fix added |
| **Migration complexity** | Medium |
| **Status** | **Candidate** — high operator value |

---

## v3.2 theme summary (draft)

| Theme | Priority | Type |
|-------|----------|------|
| Ops tooling (queue inspect, reconcile, metrics export) | P1 | Tooling + docs |
| Observability history files | P1 | Tooling |
| Event bus / audit | P2 | ADR required |
| Moderation API / multi-tenant / OTel | P3+ | Deferred |

## Out of scope (v3.2)

- Retry model redesign
- Publish semantics change
- Runtime contract schema change
- Kubernetes / multi-region
- Autonomous remediation
- Unbounded publishing

## Next step

Pass [v3_2_planning_gate.md](../releases/v3_2_planning_gate.md) → draft ADR-030 (scope TBD) on P1 items only.
