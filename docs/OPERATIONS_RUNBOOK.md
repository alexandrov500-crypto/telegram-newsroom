# Operations runbook

## Daily checks

- `python -m tools.admin_cli runtime-health --json` — DB, Redis, queue depths, worker heartbeats.
- `python -m tools.admin_cli runtime-integrity-check` — timeline + suppression JSON shape.
- If `HEALTH_HTTP_PORT>0`: `curl -fsS http://127.0.0.1:$HEALTH_HTTP_PORT/ready` (readiness).

## Queue & DLQ

```bash
python -m tools.admin_cli queue-pressure --kind ai --json
python -m tools.admin_cli dlq-list --kind publisher --limit 20
python -m tools.admin_cli dlq-inspect --kind publisher --index 0
```

Replay only after understanding the poison message: `dlq-replay` re-enqueues the original envelope.

## Redis restart

Workers use bounded Redis retries; after Redis returns, heartbeats and queues resume. If pending depth stays high, inspect `worker-queue-snapshot` and logs `redis.transport_*`.

## Emergency suppression reset

If duplicate burst / TTL suppressions block traffic incorrectly:

```bash
python -m tools.admin_cli runtime-reset-suppression
```

This clears `suppression_state.json` entries and burst counter only — **not** topic memory or cadence files.

## Safe restart

1. Stop processes (`SIGTERM` — main and workers run graceful shutdown from `app/lifecycle.py`).
2. Start Redis (if used) before workers.
3. Start DB-backed services; run `alembic upgrade head` after image upgrade if migrations ship.
4. Start `app.main` or workers; verify `/ready` and first `startup.banner` log line.

## Diagnostics bundle

```bash
python -m tools.admin_cli diagnostics-dump --limit 128 --json
```

## Incident: SQLite locked

Single writer per DB file; avoid running two schedulers against the same SQLite path. Prefer Postgres if multiple processes write.
