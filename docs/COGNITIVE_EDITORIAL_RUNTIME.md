# Cognitive Editorial Runtime

## Overview

The cognitive layer sits **above** the autonomous control plane and **below** operator agency. It continuously evaluates editorial quality, routes models intelligently, learns from outcomes, and forecasts operational pressure — while remaining explainable, auditable, and bounded.

```
┌──────────────────────────────────────────────────────────────┐
│           CognitiveEditorialRuntime (90s tick)               │
├────────────┬────────────┬────────────┬────────────┬──────────┤
│ Evaluation │ ModelRouter│ Memory+Graph│ Multi-Agent│ Learning │
├────────────┴────────────┴────────────┴────────────┴──────────┤
│ CostIntelligence │ PredictiveOps │ Simulation │ HumanFeedback │
└──────────────────────────────────────────────────────────────┘
         ▲                              │
         │         Autonomous Runtime   │  (degradation, pressure)
         └──────────────────────────────┘
```

## 1. Evaluation engine (`bot/cognitive/evaluation.py`)

- Pluggable evaluators: summary quality, publish relevance, novelty, source reliability, digest coherence
- Async `EvaluationPipeline.evaluate()` with trace steps in `evaluation_traces`
- Historical trends via `score_trend()`
- Results in `evaluation_results` (replayable via `replay_key`)

## 2. Adaptive model router (`bot/cognitive/routing.py`)

Chooses model, strategy, depth, and fallback chain based on:

- QoS class (breaking → premium model)
- Importance score
- Degradation mode
- Daily budget (`cost_budget_state`)
- Latency pressure

Audit trail: `model_route_audit`. Integration hook: `bot/cognitive/integrations.route_for_operation()`.

## 3. Editorial memory (`bot/cognitive/memory.py`)

- Story evolution, source reputation, incidents
- Bounded growth (`memory.max_entries` in policy)
- Explainable recall (`context_block()`)

## 4. Multi-agent coordination (`bot/cognitive/agents.py`)

Registered agents: breaking-news, fact-check, geopolitical, trend, quality-review, digest-curation, anomaly.

- Capability negotiation
- Bounded proposals per cycle (max 5)
- No uncontrolled publish loops — proposals are advisory

## 5. Learning coordinator (`bot/cognitive/learning.py`)

Closed-loop updates from:

- Operator feedback (promote/demote sources)
- Evaluation scores
- Publish outcomes

Bounded deltas with `rollback_last()` support. Audit: `learning_audit_log`.

## 6. Cost intelligence (`bot/cognitive/cost.py`)

- Daily budget tracking
- Low-cost degradation when spend ratio > 90%
- Spend recording via `record_spend()`

## 7. Predictive operations (`bot/cognitive/predictive.py`)

Forecasts with confidence:

- Backlog growth
- Replay storms (stream lag)
- Digest spikes
- Federation instability (DLQ)
- Publish surges

Preemptive actions: slow replay, throttle analytics, suspend federation sync.

## 8. Simulation environment (`bot/cognitive/simulation.py`)

**Production-safe lanes:** `shadow`, `offline`, `tournament`.

Scenarios: `routing_ab`, `policy_eval`, `failure_injection`, synthetic payloads.

Promotion gate: `promotion_min_score` in cognitive policy.

## 9. Human-in-the-loop (`bot/cognitive/feedback.py`)

Operator commands:

| Command | Purpose |
|---------|---------|
| `/cognitive` | Runtime status + budget |
| `/evaluate <id> [title]` | Run evaluation pipeline |
| `/route_preview [breaking]` | Preview model route |
| `/predictions` | Recent forecasts |
| `/cognitive_audit` | Cognitive decision audit |
| `/graph <node>` | Intelligence graph snapshot |

Feedback events: `operator_feedback_events`.

## 10. Intelligence graph (`bot/cognitive/graph.py`)

Connects stories, evaluations, sources, workflows, policies.

- Temporal edges in `intelligence_graph_edges`
- `lineage_query()` for replay reconstruction
- Drift detection on evaluation edges

## Database tables

`cognitive_policies`, `evaluation_results`, `evaluation_traces`, `model_route_audit`, `editorial_memory_entries`, `intelligence_graph_edges`, `cognitive_agent_registry`, `learning_audit_log`, `cost_budget_state`, `predictive_forecasts`, `simulation_runs`, `operator_feedback_events`, `cognitive_audit_log`.

## Metrics

- `cognitive_health_score`
- `cognitive_evaluation_score` (histogram)
- `cognitive_model_routes_total`
- `cognitive_spend_usd_total`
- `cognitive_predictions_total`
- `cognitive_simulation_runs_total`

## Production checklist

- [ ] Cognitive runtime enabled on operator/analysis nodes
- [ ] Daily AI budget aligned with `cost.daily_budget_usd` in policy
- [ ] Run simulation tournament in staging before routing policy changes
- [ ] Review `/cognitive_audit` after autonomous + cognitive ticks
- [ ] Wire `route_for_operation()` in processing hot paths when ready

## Architectural boundaries

| Layer | Responsibility |
|-------|----------------|
| Autonomous | Overload, recovery, degradation, topology |
| Cognitive | Quality, routing, learning, prediction |
| Editorial agents | Deterministic publish risk rules |
| Operator | Final publish authority |

Cognitive proposals **never bypass** publish idempotency, cluster policy, or degradation modes.
