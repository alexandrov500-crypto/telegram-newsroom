# Public interface freeze (Phase 3)

## Stable (do not break without version bump)

| Surface | Contract |
|---------|----------|
| `GET /health` | `status`, `dependencies`, `execution`, `runtime` keys |
| `GET /ready` | `ok` boolean semantics |
| `GET /live` | `alive`, `startup_complete` |
| `GET /ops/panel.json` | `schema_version`, `execution`, `pipeline`, `drafts` |
| `python -m newsroom.cli status` | human + `--json` summary |
| `scripts/newsroom` | subcommands: status, logs, diagnose, panel, maintenance |
| Draft statuses | `pending`, `approved`, `publishing`, `published`, `rejected`, `failed` |
| Publish journal line | `tx_id`, `draft_id`, `state`, `correlation_id`, `ts_unix` |
| `pipeline_ticks` row | `tick_id`, `status`, `started_at`, `finished_at` |
| Makefile ops | `mac-start`, `newsroom-*`, `deploy-safe` |

## Internal (may change)

| Surface | Notes |
|---------|-------|
| `POST /ops/control/*` | operator-only, not semver |
| `scheduler/jobs.py` step order | pipeline implementation |
| Editorial scoring weights | `editorial/` modules |
| `bot/*` live_ops paths | separate product surface |

## Experimental (do not rely on)

| Surface | Notes |
|---------|-------|
| `REPLAY_MODE` | ledger replay only |
| `FIRST_POST_DEBUG` / `FORCE_SINGLE_PUBLISH` | staging only |
| `deploy/live-ops/*` | multi-worker overlay |
| Redis job queue | optional transport |

## Editorial vs runtime boundary

See `docs/EDITORIAL_LAYER.md` — cosmetic changes stay in editorial; runtime layer frozen.
