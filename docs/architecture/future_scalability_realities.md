# Future scalability realities

Honest limits — no hyperscale marketing.

## Where SQLite breaks down

| Condition | Symptom | 1.x mitigation | Beyond 1.x |
|-----------|---------|----------------|------------|
| Multiple writers | Corruption risk | Single writer enforced | Remote DB + v2 program |
| Very large tables | Slow vacuum/checkpoint | Maintenance windows | Postgres ADR if measured |
| Large WAL sustained | Long checkpoint | Quiesce + PRAGMA | Not “add workers” |
| NFS/shared file DB | Locking pain | **Unsupported** | Do not deploy |

SQLite is sufficient for **single-node editorial cadence** with discipline.

## Where Redis becomes insufficient

| Condition | Reality |
|-----------|---------|
| Redis SPOF without ops | Queue stalls — not magic HA |
| Cross-region queue | **Unsupported** in-repo |
| Memory pressure | Eviction loses jobs — monitor Redis |
| No strict publish lock | Multi-worker publish risk |

Redis is a **single-node throughput tool**, not a distributed platform.

## Where Telegram workflow saturates

- API rate limits and flood-wait dominate before DB.
- Publish burst settings bound channel spam risk.
- Telethon session stability matters more than worker count.
- Multi-channel routing increases operator complexity, not linear scale.

**Scaling workers does not scale Telegram.**

## Where single-node model fails

| Workload | Verdict |
|----------|---------|
| One newsroom, daily digest | Supported (T1) |
| Parallel jobs with Redis + flags | Supported bounded (T2) |
| Multi-region active-active | **Unsupported** |
| Multi-tenant SaaS | **Unsupported** |
| 24/7 high-frequency wire | Likely needs external ops + v2 review |

## Intentionally unsupported workloads

See [unsupported_deployments.md](../scalability/unsupported_deployments.md):

- Horizontal app sharding
- K8s HA claims without external ops
- Event-sourced rewrite
- Autoscaling worker pools without discipline

## 3–5 year realistic envelope

Assume:

- 1–4 workers, 1 SQLite file, 1 Redis optional
- OUTPUT_DIR growth managed by retention
- OpenAI/Telegram as external bottlenecks
- Operator inspection remains shell + JSON

Revisit Postgres or v2 only when **documented metrics** exceed this envelope for quarters, not weeks.
