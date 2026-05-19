# Epistemic Integrity Layer

## Overview

The epistemic layer sits above the **Federated Cognitive Mesh** and answers: *how reliable is the platform's thinking?*

```
┌─────────────────────────────────────────────────────────────┐
│           EpistemicIntegrityLayer (150s tick)               │
├──────────┬──────────┬──────────┬──────────┬─────────────────┤
│Confidence│Contradic-│ Narrative│  Trust   │ Misinformation  │
│ Framework│  tions   │ Integrity│  Graph   │   Resilience    │
├──────────┴──────────┴──────────┴──────────┴─────────────────┤
│ Replay Validation │ Drift Prevention │ Human Calibration      │
├─────────────────────────────────────────────────────────────┤
│ Epistemic Governance │ Integrity Observability                │
└─────────────────────────────────────────────────────────────┘
```

## 1. Confidence framework (`bot/epistemic/confidence.py`)

Every score carries:
- `confidence`, `uncertainty`, `evidence_depth`
- `contradiction_exposure`, `source_diversity`, `replay_stability`

Bounded amplification (`MAX_CONFIDENCE_AMPLIFICATION`) and temporal decay prevent recursive inflation.

## 2. Contradiction engine (`bot/epistemic/contradiction.py`)

- `ContradictionGraph` with lineage edges
- Regional divergence, memory inconsistency, consensus disagreement
- **Minority views preserved** — no forced consensus erasure

## 3. Narrative integrity (`bot/epistemic/narrative.py`)

- Fingerprints, framing tags (urgency, attribution, sensational, conflict)
- Framing shift events, regional comparison
- Anomaly scoring for low-diversity sensational narratives

## 4. Trust graph (`bot/epistemic/trust.py`)

- Reversible trust edges with full history audit
- Trust-weighted consensus
- Operator override support

## 5. Misinformation resilience (`bot/epistemic/misinformation.py`)

Detects: low diversity, propagation bursts, replayed patterns, narrative anomalies.

Alerts require **operator review** (`pending_review` status).

## 6. Epistemic replay (`bot/epistemic/replay.py`)

Validates consensus and confidence stability under replay (`epistemic` lane).

## 7. Drift prevention (`bot/epistemic/drift.py`)

Tracks: consensus homogenization, source monoculture, overconfident routing.

## 8. Human calibration (`bot/epistemic/calibration.py`)

Operator commands for confidence lineage, contradictions, trust override, alert validation.

## 9. Epistemic governance (`bot/epistemic/governance.py`)

Invariants: truth integrity, uncertainty disclosure, minority preservation, reversible trust.

## 10. Observability (`bot/epistemic/observability.py`)

Snapshots: confidence heatmap, contradiction network, trust evolution, misinfo pressure, drift timeline.

### Operator commands

| Command | Purpose |
|---------|---------|
| `/epistemic` | Integrity status |
| `/confidence <type> <id>` | Confidence lineage |
| `/contradictions` | Open contradiction explorer |
| `/trust <from> <to> <score>` | Override trust (reversible) |
| `/analyze_story <id> [title]` | Full epistemic story analysis |

### Metrics

- `epistemic_stability_score`
- `misinformation_pressure_score`
- `epistemic_open_contradictions`
- `epistemic_alerts_total`
- `epistemic_replay_runs_total`

## Design principles

| Principle | Implementation |
|-----------|----------------|
| Explainability | Every score/alert includes `explanation` |
| Reversibility | Trust history + operator override |
| Minority preservation | Contradictions stored with minority JSON |
| No silent erasure | Governance blocks forced consensus |
| Operator supremacy | High-severity alerts need review |

## Production checklist

- [ ] Review `/contradictions` after mesh consensus sessions
- [ ] Validate misinformation alerts before quarantine actions
- [ ] Run epistemic replay after policy promotions
- [ ] Monitor `epistemic_stability_score` alongside `mesh_health_score`
