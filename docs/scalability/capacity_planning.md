# Capacity planning (production-lite)

Heuristics for operators — not hyperscale capacity models.

## Expected workload ranges

| Signal | Comfortable | Investigate | Stop scaling |
|--------|-------------|-------------|--------------|
| Pending queue depth (per kind) | < 50 | 50–200 | > 200 sustained |
| Retry burst (`retry_burst_window`) | < 40% of storm threshold | ≥ threshold | Sustained at threshold |
| SQLite WAL | < 64 MB | 64–256 MB | > 256 MB |
| `OUTPUT_DIR` total | < 200 MB | 200–500 MB | > 500 MB without retention |
| Scheduler overlap events | 0 | 1–2 / day | Frequent overlap |

## Safe queue sizes

- Target pending depth **< 50** per job kind under steady state.
- Burst absorption: allow short spikes to **~100** if workers catch up within 15 minutes.
- If pending + processing > **200** for > 30 minutes: fix upstream failures before adding workers.

## Retry saturation thresholds

- Default storm detection: `RUNTIME_RETRY_STORM_COUNT=40` in `RUNTIME_RETRY_STORM_WINDOW_SEC=60`.
- Do not increase workers while burst is at threshold — amplifies contention.
- Enable `WORKER_RETRY_SAFE=1` before scaling workers in T2.

## WAL growth expectations

- Steady editorial load: WAL often < 10 MB between checkpoints.
- Bulk import / replay: WAL can spike; checkpoint after quiesce.
- **> 256 MB WAL:** high risk of long checkpoint and restore coupling — see WAL_PRESSURE runbook.

## Redis usage expectations

- One Redis instance per T2 node; no cluster requirement in-repo.
- Reconnect churn: if transport metrics show repeated failures, stabilize Redis before workers > 2.

## OUTPUT_DIR growth estimates

- Nightly full inspection: ~1–5 MB per run (varies with pipeline).
- Unpruned month: can exceed **500 MB** — schedule `evidence_retention` / `runtime_retention`.

## Snapshot sizing guidance

- 12 frozen runtime artifacts + indexes: baseline small JSON.
- Growth driver: historical nightly copies under `OUTPUT_DIR/runtime/`.
- Rule of thumb: restore time ≈ **0.02 s per MB** copy-only (local disk); validate with drills.

## Restore timing expectations

| Bundle size | Rough local restore |
|-------------|---------------------|
| < 50 MB | seconds |
| 50–200 MB | tens of seconds |
| > 200 MB | minutes; plan maintenance window |

## Operator warning thresholds

Run periodically:

```bash
python3 tools/scalability_diagnostics.py --output-dir "$OUTPUT_DIR" --database-url "$DATABASE_URL"
```

Treat `HIGH` findings as scale-stop signals.

## Practical sizing heuristics

- **1 worker + T1:** simplest; fits most editorial cadence.
- **2–4 workers + T2:** only with Redis + strict flags; monitor queue and retry burst.
- **More workers:** diminishing returns; SQLite and publish lock serialize hot paths.

## When NOT to scale further

- Retry storm active
- WAL > 256 MB without checkpoint
- Redis unstable
- `PUBLISH_LOCK_STRICT` off with multiple workers
- Evidence disk > 80% full
- Scheduler overlap frequent

Scaling out workers without fixing these **increases** failure rate (retry amplification).
