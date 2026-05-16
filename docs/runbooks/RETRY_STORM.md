# RETRY_STORM

## Symptoms

- Worker logs spam `worker.job_retry`
- Queue depth grows; `runtime_retry_storm` watchdog warnings
- OpenAI / Telegram rate limit messages

## Detection

- Counters: `openai_retries`, worker retry traces (diagnostics buffer)
- `RUNTIME_RETRY_STORM_COUNT` threshold exceeded in watchdog
- DLQ not draining

## Immediate Mitigation

1. Identify failing job type in DLQ samples.
2. Fix upstream (API key, rate limit, bad payload) — do not only restart workers.
3. Optional: `WORKER_RETRY_SAFE=1` to reduce ack-then-enqueue loss risk during storm.

## Safe Recovery

1. Drain or purge poison messages from DLQ after root-cause fix.
2. Restart workers with backoff-friendly settings unchanged unless ADR-approved.
3. Run bounded pipeline tick manually.

## Validation Steps

- Retry rate returns to baseline over 2+ poll intervals
- `make runtime-index` shows no new FAIL on required artifacts

## Rollback Strategy

Revert env changes; restore queue from backup only if corruption proven (rare).

## Evidence Collection

- DLQ JSON samples (`tools/admin_cli.py` or `/ops/dlq`)
- `retry_traces_snapshot()` in diagnostics tests / support bundle
- OpenAI error codes from logs

## Escalation Notes

Legacy retry order (`WORKER_RETRY_SAFE=0`) can lose jobs if enqueue fails after ack — document in postmortem.
