# Editorial governance

Production-grade explainability, deterministic ranking, declarative policies, and operator controls. No LLM ranking or vector stores.

## Components

| Module | Role |
|--------|------|
| `editorial/governance/ledger.py` | Append-only JSONL decision log |
| `editorial/governance/ranking.py` | Weighted deterministic ranking + trace |
| `editorial/governance/policies_engine.py` | Reloadable declarative rules |
| `editorial/governance/reputation.py` | Slow EMA over `source_reputation.json` |
| `editorial/governance/diversity_controls.py` | Topic/source cooldowns + metrics |
| `editorial/governance/operator_controls.py` | Mutes, freeze, boosts (audited) |
| `editorial/governance/explainability.py` | Draft `editorial_governance` extras |
| `editorial/governance/drift.py` | Concentration / entropy warnings |

## HTTP (ops token)

- `GET /runtime/editorial/ranking` — weights + last ranking snapshot
- `GET /runtime/editorial/policies` — active governance rules
- `GET /runtime/editorial/ledger` — recent decision records
- `GET /runtime/editorial/status` — reputation, diversity, operator controls, drift

## Runtime files

Under `{RUNTIME_STATE_DIR}/editorial/`:

- `decision_ledger.jsonl` — bounded append-only (env: `EDITORIAL_LEDGER_MAX_LINES`, `EDITORIAL_LEDGER_MAX_BYTES`)
- `ranking_weights.json` — stage weights (reload without deploy)
- `governance_rules.json` — policy rules
- `operator_controls.json` — mutes / freeze / boosts
- `governance_state.json` — cooldowns, EMA, distribution counters
- `last_ranking_snapshot.json` — last deterministic rank run

## Operator commands (admin DM)

- `/editorial_freeze on|off` — emergency stop for new cluster selection
- `/mute_source <channel> [minutes]`
- `/boost_source <channel> [boost]`

All actions append to the decision ledger.

## Ranking stages

Default weights (configurable in `ranking_weights.json`):

1. freshness  
2. source_reputation  
3. novelty  
4. topic_diversity  
5. engagement  
6. duplicate_suppression (penalty)  
7. operator_boost / block  

Tie-break: `(-total, -newest_post_id, -cluster_size, fingerprint)`.

## Drift

Heartbeat runs `check_editorial_drift`; warnings log as `editorial.drift.warning` when topic/source concentration or duplicate suppressions rise.

## Replay

1. Copy runtime `editorial/` dir into a test `RUNTIME_STATE_DIR`.  
2. Re-run `rank_clusters` with the same candidate payloads → identical `trace` if weights unchanged.  
3. `query_decisions` replays historical suppress/select/publish decisions.

See `docs/examples/editorial/` for sample JSON.
