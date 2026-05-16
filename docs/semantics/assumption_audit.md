# Operational assumption audit

Implicit assumptions made explicit.

## Implicit assumptions

| Assumption | Impact if false | Mitigation | Unsupported outcome |
|------------|-----------------|------------|---------------------|
| One SQLite writer | Corruption | Enforce single app + worker writer policy | Multi-master |
| Local POSIX filesystem | Slow/corrupt I/O | Local SSD; avoid NFS | Network DB file |
| Redis reachable when enabled | Queue stall | T1 fallback; fix Redis | Silent split queue |
| Operator runs nightly | Blind drift | Calendar + alerts | Auto-heal |
| Clock roughly monotonic | Retry/jitter skew | NTP on host | Strict ordering proofs |
| Tokens valid | Auth failures | rotation runbooks | Guaranteed publish |
| OpenAI available | Pipeline gaps | backoff, DLQ | SLA claims |

## Operator trust assumptions

- Operators read PASS/WARN/FAIL literally.
- Operators quiesce before restore.
- Operators do not commit secrets to OUTPUT_DIR.
- Destructive actions are manual.

## Filesystem assumptions

- `OUTPUT_DIR` has free space for nightly.
- Atomic rename available for typical deploys.
- Copy-based restore is valid when quiesced.

## Redis assumptions

- Single Redis instance per node (default).
- `SET NX EX` semantics as documented by Redis version in use.
- Prefix isolation via `job_queue_prefix`.

## SQLite assumptions

- `journal_mode=WAL` acceptable for workload.
- Migrations applied before workers start.
- Backup = file copy when quiesced.

## Telegram API assumptions

- Rate limits external to repo.
- Session string stored securely.
- Channel permissions stable.

## Clock / time assumptions

- `retry_burst_window` uses monotonic/wall reasonably aligned.
- Scheduler uses host timezone config.
- No distributed clock sync required (single node).

## Backup discipline assumptions

- Operators retain at least one complete OUTPUT_DIR or bundle.
- Freshness checked via recovery intelligence heuristics.
- Drills performed periodically.

## Mitigation summary

Use read-only tools: `semantics_guardrails.py`, `scalability_diagnostics.py`, `architecture_guardrails.py`, `validate-recovery`.
