# Federated Cognitive Mesh

## Overview

The mesh transforms the centralized cognitive runtime into a **distributed collaborative intelligence fabric** — region-aware, consensus-safe, replay-coherent, and constitutionally governed.

```
┌─────────────────────────────────────────────────────────────────┐
│              FederatedCognitiveMesh (120s tick)                   │
├──────────┬──────────┬──────────┬──────────┬──────────┬───────────┤
│ Cognitive│ Agent    │ Federated│ Collective│ Federated│ Cognitive │
│ Bus      │ Mesh     │ Memory   │ Reasoning │ Learning │ Resilience│
├──────────┴──────────┴──────────┴──────────┴──────────┴───────────┤
│ Simulation Arena │ Intelligence Economics │ Constitutional Gov   │
├──────────────────────────────────────────────────────────────────┤
│                    Mesh Observability                             │
└──────────────────────────────────────────────────────────────────┘
         ▲                    ▲
         │                    │
  Operational EventBus   CognitiveEditorialRuntime
```

## 1. Federated Cognitive Bus (`bot/mesh/bus.py`)

- **CognitiveEventEnvelope** — separate from operational `EventEnvelope`
- Lanes: `gossip`, `quorum`, `regional`, `evaluation`, `memory`, `learning`
- Bounded gossip budget per tick (storm prevention)
- Dedup via `mesh_cognitive_events.event_id`
- Causal ordering via `sequence_num` + `causation_id`
- Quorum/memory/learning lanes sync via `federated_learning_sync`

## 2. Distributed Agent Fabric (`bot/mesh/agents.py`)

- **AgentMeshRegistry** — leases in `mesh_agent_leases`
- Capability marketplace across nodes/regions
- Task allocation with regional affinity
- Evaluation sharing via cognitive bus

## 3. Shared Cognitive Memory (`bot/mesh/memory.py`)

- Regional shards in `mesh_memory_shards`
- Vector-clock reconciliation (explainable winner selection)
- Lineage in `mesh_memory_lineage`
- Rollback to preferred region

## 4. Collective Editorial Reasoning (`bot/mesh/reasoning.py`)

- Weighted consensus (not opaque averaging)
- Disagreement tracking + minority opinion preservation
- Votes in `mesh_consensus_votes`, sessions in `mesh_reasoning_sessions`

## 5. Federated Learning (`bot/mesh/learning.py`)

- Regional deltas in `mesh_learning_deltas`
- Evaluation-weighted aggregation
- Operator approval gate via constitution
- Rollback via local `LearningCoordinator`

## 6. Cognitive Resilience (`bot/mesh/resilience.py`)

- Mesh health scoring, trust decay, node quarantine
- Memory desync detection + repair workflows
- Graceful recommendations under uncertainty

## 7. Federated Simulation Arena (`bot/mesh/simulation.py`)

- Tournaments in `mesh_simulation_tournaments`
- Lane `mesh_shadow` — never mutates production cognition
- Constitutional gate + regional simulation budget

## 8. Intelligence Economics (`bot/mesh/economics.py`)

- Per-region quotas in `mesh_cognitive_budgets`
- Adaptive reasoning depth, agent slots, memory replicas
- Cross-region pressure balancing

## 9. Constitutional Governance (`bot/mesh/governance.py`)

- Invariants: operator supremacy, no unaudited publish, no policy self-modify, replay coherence, bounded autonomy
- Protected actions require operator approval
- Simulation-before-promotion gate

## 10. Mesh Observability (`bot/mesh/observability.py`)

Snapshots: propagation graph, regional heatmap, consensus timeline, agent collaboration, learning timeline.

### Operator commands

| Command | Purpose |
|---------|---------|
| `/mesh` | Mesh health + budget |
| `/mesh_agents` | Capability marketplace |
| `/mesh_consensus [topic]` | Open reasoning session |
| `/mesh_explain <session_id>` | Consensus lineage |
| `/mesh_tournament` | Run shadow tournament |

### Metrics

- `mesh_health_score`
- `mesh_cognitive_events_total`
- `mesh_consensus_sessions_total`
- `mesh_simulation_tournaments_total`
- `mesh_gossip_budget_remaining`

## Production checklist

- [ ] Enable mesh on operator nodes with cluster coordination
- [ ] Set regional budgets in `mesh_cognitive_budgets`
- [ ] Review constitution before policy promotions
- [ ] Run `/mesh_tournament` in staging before routing changes
- [ ] Monitor `mesh_health_score` and gossip budget exhaustion

## Architectural boundaries

| Layer | Scope |
|-------|-------|
| Operational bus | Ingest, publish, signals |
| Cognitive bus | Evaluations, memory, learning, agent coordination |
| Cognitive runtime | Local scoring, routing, simulation |
| Mesh | Federation, consensus, governance |
| Operator | Final authority on policy and publish |
