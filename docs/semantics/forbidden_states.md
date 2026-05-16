# Forbidden state registry

States the system does **not** support operationally. Not exhaustive of all bugs — explicit anti-configurations.

## Unsupported runtime combinations

| State | Why forbidden | Symptoms | Operator response | Recoverability |
|-------|---------------|----------|-------------------|----------------|
| Multi-worker + `PUBLISH_LOCK_STRICT=0` + Redis | Split-brain publish | Duplicate posts | Set strict=1 or workers=1 | Medium — audit channel |
| `PUBLISH_LOCK_STRICT=1` + `REDIS_ENABLED=0` | Strict cannot lock | Publish denied | Enable Redis or disable strict | High after config fix |
| Shared SQLite on NFS | Writer locking broken | Corruption, stalls | Local disk only | Low if corrupted |
| Two app instances, one DB file | Dual writers | Corruption | Single instance | Low |

## Inconsistent recovery states

| State | Why forbidden | Symptoms | Response | Recoverability |
|-------|---------------|----------|----------|----------------|
| Restore DB while workers running | Torn pages | Crash, checksum fail | Quiesce all writers | Medium |
| `verify-runtime` OK but manifest stale | False confidence | Drift undetected | Re-run nightly | High |
| Mixed 1.x artifact schema in one OUTPUT_DIR | Compatibility break | check-compatibility FAIL | Single generation source | High |

## Unsafe multi-worker states

| State | Why forbidden | Symptoms | Response | Recoverability |
|-------|---------------|----------|----------|----------------|
| Retry storm + scale-out | Amplification | DLQ growth | workers=1; fix upstream | Medium |
| Redis flapping + multi-worker | Lock/queue chaos | Reconnect metrics | Stabilize Redis | Medium |
| `WORKER_RETRY_SAFE=0` + high churn | Lost retries | Missing jobs | Enable safe retry | Low for lost jobs |

## Invalid retention states

| State | Why forbidden | Symptoms | Response | Recoverability |
|-------|---------------|----------|----------|----------------|
| Prune required artifacts | Contract break | sanity check FAIL | Restore from archive | Medium |
| Disk full mid-nightly | Partial write | Incomplete runtime/ | Free space; re-run | High |
| Zero retention + no archive | No history | Cannot compare-baseline | External archive | N/A |

## Broken restore states

| State | Why forbidden | Symptoms | Response | Recoverability |
|-------|---------------|----------|----------|----------------|
| Bundle missing `runtime_manifest.json` | Cannot verify | validate-recovery FAIL | Use complete bundle | High if backup exists |
| Checksum mismatch ignored | Silent drift | verify-runtime WARN ignored | Stop promote; investigate | Medium |

## Partial recovery states

| State | Why forbidden | Symptoms | Response | Recoverability |
|-------|---------------|----------|----------|----------------|
| DB restored, OUTPUT_DIR old | Inspection lies | recovery_report inconsistent | Align timestamps | High |
| Redis flushed, SQLite has pending flags | Orphan state | Stuck publishes | Reconcile manually | Medium |

## Stale lock edge cases

| State | Why forbidden | Symptoms | Response | Recoverability |
|-------|---------------|----------|----------|----------------|
| Redis lock TTL expired mid-publish | Overlap risk | double publish rare | Strict + short jobs | Low |
| `publish_lock` key orphaned after crash | Contention until TTL | publish skipped | Wait TTL or delete key | High |

## Unsafe Redis fallback combinations

| State | Why forbidden | Symptoms | Response | Recoverability |
|-------|---------------|----------|----------|----------------|
| Strict off + Redis error → local lock | Per-process only | Duplicates across workers | strict=1 or one worker | Medium |
| In-memory queue in multi-process | No shared queue | Lost jobs | Use Redis | Low |

See [recovery_semantics.md](recovery_semantics.md) for guaranteed vs non-guaranteed recovery.
