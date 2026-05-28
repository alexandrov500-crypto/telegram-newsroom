# Pipeline stall

## Symptoms

- `pipeline_stalled` operator alert
- `pipeline_ticks` row stuck in `running`
- No `scheduler.pipeline_tick` end logs

## Diagnosis

```bash
curl -s http://127.0.0.1:8080/ops/panel.json | python3 -c "import sys,json; p=json.load(sys.stdin); print(p.get('pipeline'))"
grep pipeline_tick.stale logs/local-run.log | tail -5
grep invariant.violation logs/local-run.log | tail -5
```

## Fix

```bash
# Restart worker (releases lease + scheduler)
bash scripts/stop_local_newsroom.sh && make mac-start

# Clear stale tick rows (optional, SQLite)
# UPDATE pipeline_ticks SET status='stale' WHERE status='running';
```

## Expected

Next tick: `status=ok`, `duration_ms` reasonable.
