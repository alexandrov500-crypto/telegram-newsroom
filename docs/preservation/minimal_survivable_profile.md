# Minimal survivable runtime profile

**Minimum recoverable system** — not minimum feature set.

## Smallest supported deployment (T1 survivable)

| Component | Required |
|-----------|----------|
| Host | 1 Linux/macOS node, local disk |
| Python | Floor per `pyproject.toml` (currently ≥3.12) |
| SQLite | Single file, local path |
| Processes | `app.main` + optional single worker |
| Redis | **Not required** |
| OUTPUT_DIR | Writable path for inspection |
| Secrets | Telegram + OpenAI via env |

## Minimum required tooling (operator)

| Tool | Purpose |
|------|---------|
| `python3`, `pip` | Run app |
| `make` | Inspection shortcuts |
| Shell | `runtime-nightly`, verify, recovery |

CI toolchain (pytest, ruff) **not** required for survivable runtime.

## Minimum operational dependencies

- Network egress to Telegram + OpenAI
- Disk for DB + OUTPUT_DIR (retention-bounded)
- No K8s, no Postgres, no Prometheus

## Fallback operational mode

| Mode | When | Capability |
|------|------|------------|
| **T1 single-node** | Redis down / avoid complexity | Editorial + inspection degraded queue |
| **T3 inspection-only** | No live publish | verify-runtime, validate-recovery from archive |
| **Read-only guardrails** | Any | All `*_guardrails.py` tools |

## Degraded survivable mode

- Workers stopped; app read-only or stopped
- Inspection from last good OUTPUT_DIR
- Strict publish lock deny preferred over duplicate publish
- `WORKER_RETRY_SAFE=0` only if single worker and accepted risk

## Not minimal (do not claim survivable without)

- Multi-worker without Redis
- Shared NFS SQLite
- Partial `runtime/` as “good enough”
- Missing manifest for verify-runtime

## Recovery proof checklist

```bash
make runtime-nightly   # if live
make verify-runtime OUTPUT_DIR=...
make validate-recovery OUTPUT_DIR=...
python3 tools/preservation_guardrails.py
```

See [long_horizon_recovery.md](long_horizon_recovery.md).
