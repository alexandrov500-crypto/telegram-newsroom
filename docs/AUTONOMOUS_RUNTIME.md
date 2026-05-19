# Autonomous Self-Healing Editorial Runtime

## Overview

The cluster autonomously manages overload, regional instability, workflow recovery, and degradation — while remaining **explainable** and **operator-overridable**.

```
┌─────────────────────────────────────────────────────────┐
│              AutonomousRuntime (45s tick)               │
├─────────────┬──────────────┬──────────────┬─────────────┤
│ PolicyRuntime│ AdaptiveScheduler│ IntelligentRecovery│ OpsEngine │
├─────────────┴──────────────┴──────────────┴─────────────┤
│ DegradationStateMachine │ TopologyIntelligence │ QoS │ ReplayGuard │
└─────────────────────────────────────────────────────────┘
```

## 1. Policy engine (`bot/policy/`)

- **Declarative JSON** policies in `cluster_policies` (versioned, hot reload)
- **PolicyEvaluator** — node admission, workflow throttle, publish limits, federation, regional routing
- **PolicyRuntime** — audit trail, cluster propagation via `federated_learning_sync`
- Operator: `/policy_audit`

## 2. Adaptive scheduler (`bot/runtime/adaptive_scheduler.py`)

- Load signals: backlog, stream lag, DLQ, stalled workflows
- QoS-weighted lease TTL (breaking > digest > analytics)
- Load shedding under pressure
- Digest scheduler uses `try_schedule(..., qos_class="digest")`

## 3. Intelligent recovery (`bot/runtime/intelligent_recovery.py`)

- Failure classification: transient, permanent, rate_limit, partition, poison
- Exponential backoff from policy
- Topology/redis/telegram signals
- Stuck workflow graph analysis

## 4. Multi-region (`bot/runtime/region.py`)

- Region health scores from topology
- Failover routing via policy `regional_failover`
- Quorum checks

## 5. Editorial QoS (`bot/runtime/editorial_qos.py`)

Priority order: breaking → publish → digest → enrichment → media → federation → analytics → backfill

Latency budgets and starvation detection.

## 6. Degradation modes (`bot/runtime/degradation.py`)

| Mode | Effect |
|------|--------|
| `normal` | Full operation |
| `publish_safe` | Throttle non-breaking publish |
| `degraded_federation` | Pause federation sync |
| `read_only` | No publishes |
| `replay_only` | Recovery focus |
| `operator_only` | Manual control |

Operator: `/degradation <mode>` or `/degradation` (status)

## 7. Topology intelligence (`bot/runtime/topology.py`)

- Live node/region/partition graph
- Hot partition detection
- Rebalance recommendations
- Persisted snapshots
- Operator: `/topology`

## 8. Operational decisions (`bot/runtime/operations.py`)

Leader-only autonomous actions (when `apply_operations=True`):

- Drain unhealthy nodes
- Transition degradation on backlog/lag/DLQ
- Regional federation pause
- Rollback when health recovers

## 9. Replay guard (`bot/runtime/replay_guard.py`)

- Checkpoints in `replay_checkpoints`
- Rate-limited replay lanes
- Publish-safe replay (requires idempotency store)

## 10. Chaos testing (`bot/chaos/runner.py`)

```python
await run_chaos_suite(recovery=..., idempotency=..., scheduler=..., degradation=..., coordination=...)
```

Scenarios: node kill recovery, duplicate publish, stream lag shedding, degradation transitions, partition pause.

## Failure modes

| Scenario | Autonomous response |
|----------|---------------------|
| EU ingest degraded | Regional score drops → federation pause, failover routing |
| US digest lagging | Hot partition + shed analytics |
| Redis stall | Transient recovery, DLQ pressure → degrade |
| Telegram rate limit | Classify rate_limit, backoff 30s+ |
| Rolling upgrade | `node_admission` envelope version check |

## Production checklist

- [ ] Leader node runs `apply_operations=True` (only one leader)
- [ ] Policy propagated via shared PostgreSQL coordination
- [ ] Grafana: `topology_health_score`, `scheduler_pressure_score`, `degradation_mode_active`
- [ ] Run chaos suite in staging after deploy
- [ ] Document operator override paths (`/degradation`, drain commands)
