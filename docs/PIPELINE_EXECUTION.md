# Pipeline execution (30-second model)

## Linear tick flow

```
scheduler tick
  → collect (optional ingest)
  → summarize (OpenAI OR unified rule fallback → draft OR reject idle reason)
  → publish step (optional; separate from tick terminal)
  → media enrich on draft insert (non-blocking; never changes terminal)
  → finalize_pipeline_tick (ONE resolver → ONE DB finish)
```

## Terminal outcomes (only three)

| `terminal_state`     | Meaning                          | `status` |
|----------------------|----------------------------------|----------|
| `committed_draft`  | Draft persisted this tick        | `ok`     |
| `committed_reject` | Explicit reject (desk, AI, etc.) | `reject` |
| `committed_idle`   | No backlog / nothing to do       | `ok`     |

Resolver: `app/reliability/terminal_state_resolver.py`  
Finalizer: `app/reliability/tick_finalizer.py` (single call per tick)

## Summarization fallback (one handler)

`app/reliability/summarize_fallback.summarize_openai_or_fallback` — no parallel fallback branches in `scheduler/jobs.py`.

## Publish (separate gate stack)

One decision function: `app/ops/execution_gates.evaluate_publish_gate`

Precedence: `GLOBAL_PUBLISH_PAUSE` → `runtime_control` PAUSED → `operational_mode` → auto_maintenance halt.

`publish.audit` is logged **before** Telegram send (allowed or blocked).

## Control plane precedence

| Layer              | Scheduler | Publish | Precedence        |
|--------------------|-----------|---------|-------------------|
| `operational_mode` | yes       | yes     | env > persisted   |
| `runtime_control`  | no        | yes     | env > persisted > inferred burn-in flags |

`GLOBAL_PUBLISH_PAUSE` blocks publish only; does not rewrite stored control mode.

## Execution graph verification (VPS observation mode)

Runtime traces each tick (diagnostics only; **CRITICAL** activates safe recovery):

- `execution_graph.tick_begin` / `summarize_path` / `publish_gate` / `finalize`
- `execution_graph_anomaly_detected` with `severity=warning|critical`
- **WARNING** — log only (e.g. `delayed_finalize`, `tick_overlap`)
- **CRITICAL** — tick marked corrupted in `detail_json`, publish blocked, excluded from stability metrics (e.g. `duplicate_finalize`, `publish_without_gate_allowed`)
- `execution_graph.safe_recovery_activated` when CRITICAL fires

Report:

```bash
make execution-graph-report   # → var/runtime/execution_graph_report.json
```

PUBLIC GO requires `execution_graph_ready=true` (100% consistency over trace window, zero log anomalies).

## Burn-in checks

```bash
make burnin-check
make stability-report
make execution-graph-report
make public-go-check
```
