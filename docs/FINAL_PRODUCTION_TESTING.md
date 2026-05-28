# Final production testing (pre-public freeze)

This phase validates launch readiness using the **RELEASE_CONTRACT** model only.
No new features or architecture changes are allowed during this freeze.

## Scope rules

- REQUIRED contract fields are hard gates.
- OBSERVATIONAL fields are confidence signals only (`UNKNOWN` never blocks REQUIRED).
- Environment (`LOCAL_DEV`, `VPS_BURNIN`, `PRODUCTION`) never changes REQUIRED logic.

## Local / VPS procedure

1. Ensure runtime DB and logs exist (`data/newsroom.db`, `logs/local-run.log`).
2. Set production-like env on VPS (`ENV=production`, `NEWSROOM_RUNTIME_PROFILE=vps`).
3. Run the full suite:

```bash
make final-production-test
```

4. Optional strict gate mode (required fields only):

```bash
python3 tools/final_public_check.py --test-mode-final-gate
```

## Artifacts (under `var/runtime/`)

| File | Purpose |
|------|---------|
| `final_e2e_production_test_report.json` | Controlled E2E invariant scenarios |
| `telegram_safe_simulation_report.json` | Telegram-safe simulation (zero real posts) |
| `system_consistency_report.json` | `CONSISTENT` / `INCONSISTENT` |
| `final_public_check_report.json` | Contract verdict |
| `final_release_readiness_report.json` | Aggregated launch verdict |
| `final_production_test_summary.json` | CLI summary |

## Go / no-go criteria

**GO (READY_FOR_PUBLIC)** when:

- `FINAL_RELEASE_READINESS_VERDICT=READY_FOR_PUBLIC`
- `SYSTEM_CONSISTENCY_VERDICT=CONSISTENT`
- all REQUIRED contract fields are `PASS`
- Telegram safe simulation `ok=true`
- E2E production test `ok=true`

**CONDITIONAL** when REQUIRED pass but observational signals are incomplete or degraded.

**NO-GO (NOT_READY)** when any REQUIRED violation, inconsistency, duplicate publish, ordering break, or rollback leakage is detected.

## Operator Telegram commands

- `/go_status` — READY / CONDITIONAL / NOT READY + top blockers
- `/release_status` — rollout stage + readiness
- `/runtime_state` — protection + readiness snapshot
- `/continuity` — continuity score (UNKNOWN if missing)
- `/final_check` — last contract evaluation artifacts

## Rollback / emergency

1. Enable rollback: `LIVE_ROLLBACK_MODE=true` and restart, or operator `/pause_autopublish`.
2. Verify `/rollback_status` and `/final_check`.
3. Diagnose using `make final-production-test` and inspect `system_consistency_report.json`.
4. Resume only after REQUIRED contract returns to PASS: `/resume_autopublish`.

## First 24h watch

- Run `make final-production-test` after deploy and every 6h during burn-in.
- Monitor `/go_status`, `/continuity`, `/runtime_state`.
- Alert on `required_failed:*` or `SYSTEM_CONSISTENCY_VERDICT=INCONSISTENT`.
