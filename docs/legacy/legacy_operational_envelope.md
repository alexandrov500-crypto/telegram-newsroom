# Legacy operational envelope

Bounded operations after dormancy or in maintenance-only mode.

## Minimum supported topology

| Topology | Legacy support |
|----------|----------------|
| **T1** single-node production-lite | **Primary legacy** |
| **T3** inspection / recovery only | **Supported** |
| **T2** multi-worker + Redis + flags | Supported if redis maintained |
| **T4** distributed / multi-region | **Unsupported** |

See [operational_topologies.md](../scalability/operational_topologies.md).

## Acceptable degraded operation

| Degraded mode | Acceptable when |
|---------------|-----------------|
| Workers stopped; app inspect-only | Recovery / audit |
| Redis down; single worker | T1 fallback |
| WARN verify-runtime (optional missing) | Not promotion baseline |
| Strict publish deny | Safer than duplicate publish |
| Advisory intelligence ignored | Operator choice |

## Unsupported future workloads

- Hyperscale queue depth
- Multi-tenant SaaS
- Mandatory external observability stack
- Autonomous self-healing
- Real-time wire-scale ingestion without uplift

## Operational constraints after dormancy

1. Re-read [ecosystem_continuity.md](../stewardship/ecosystem_continuity.md) post-dormancy section.
2. Run `make legacy-validate` + `make preservation-validate`.
3. Enable opt-in flags one at a time.
4. Do not scale workers before queue/retry green.
5. Prefer tag checkout over untested `main`.

## Bounded expectations under ecosystem drift

| Drift | Legacy response |
|-------|-----------------|
| Python EOL | Uplift branch; update requires-python |
| OpenAI model gone | Change model env; patch client if needed |
| Telegram breaking change | Telethon/aiogram pin bump |
| Redis protocol | redis package pin bump |

**Not in scope:** automatic adapters for all future APIs.

## Legacy inspection cadence (suggested)

| Frequency | Action |
|-----------|--------|
| Quarterly | security-validate (if network available) |
| Annual | recovery drill + preservation-validate |
| On incident | semantics + scaling runbooks |

No mandatory cron in-repo.
