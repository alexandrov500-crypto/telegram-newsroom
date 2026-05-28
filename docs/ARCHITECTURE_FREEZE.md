# Architecture freeze — public burn-in

**Status: ARCHITECTURE FINALIZED FOR PUBLIC BURN-IN**

## Policy

| Rule | Detail |
|------|--------|
| Structural changes | **Not allowed** during burn-in |
| Permitted work | Stabilization, bug fixes, observability, ops safeguards only |
| Migrations | Major refactors **only after** controlled public launch |

## Frozen boundaries

These boundaries are fixed for burn-in. Extend behavior only via configuration and documented ops toggles.

```
Telegram sources → collector → ingestion ledger → scheduler tick
    → desk / editorial → draft → media (non-blocking) → publish journal → channel
```

- **Single publish path:** `publisher.publish_service.execute_admin_publication_flow`  
- **Terminal states only:** `committed_draft`, `committed_reject`, `committed_idle` (`ok` / `reject` tick status)  
- **Single runtime per `BOT_TOKEN`:** flock + leadership + `RUNTIME_NODE_ROLE`  
- **Operational mode file:** `var/runtime/operational_mode.json` (scheduler/publish gates)  
- **Runtime control file:** `var/runtime/runtime_control.json` (operator degradation ladder)  

## Operator control model (frozen)

| Mode | Scheduler | Publish | Media | Fallback |
|------|-----------|---------|-------|----------|
| `NORMAL` | on | on | on | primary when healthy |
| `SOFT_DEGRADED` | on | on | on | fallback allowed |
| `HARD_DEGRADED` | on | on | on | fallback + relaxed burn-in governance |
| `TEXT_ONLY` | on | on | off | fallback as configured |
| `PAUSED` | on | **off** | n/a | n/a |

Mode changes are **never silent**: logged as `runtime.degraded_mode_changed` and persisted.

## Publish safety (frozen)

- `GLOBAL_PUBLISH_PAUSE=true` — hard block on all channel sends  
- Idempotency journal + `publish.idempotent_skip` — no duplicate Telegram posts  
- `publish.audit` — decision, mode, source tick correlation  
- `FINAL_STAGING_MODE` / `AUTO_PUBLISH_ENABLED` — autonomous publish policy unchanged; see `app/ops/autonomous_publish.py`  

## Observability (frozen additions)

- `system_stability_score` — low-variance burn-in metric (`make stability-report`)  
- Health: `/health/components`, `/health/pipeline`, runtime report JSON  
- Burn-in: `tools/burnin_validation.py`, `make burnin-check`  

## What not to do

- Split scheduler into new worker topology  
- Add second publish pipeline or parallel bot send paths  
- Introduce new ranking / intelligence modules in the hot path  
- Replace SQLite tick ledger without migration plan post-launch  

## Exit criteria for architecture unfreeze

1. Burn-in PASS for 3–7 days on VPS  
2. At least one verified channel publish with media/text parity  
3. Signed ops approval for controlled public exposure  

Until then: **boring, predictable, self-healing** — see [FEATURE_FREEZE.md](./FEATURE_FREEZE.md).
