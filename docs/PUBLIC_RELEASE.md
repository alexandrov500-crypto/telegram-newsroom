# Controlled public release

## Final launch checklist

1. VPS burn-in ≥ 3 days with `make burnin-check` → PASS  
2. `make execution-graph-report` → `execution_graph_ready=true`, zero CRITICAL  
3. `make stability-report` → acceptable scores  
4. `make release-readiness` → `FINAL_PUBLIC_READINESS: READY`  
5. `make public-go-check` → PASS  
6. One manual channel publish verified (`/preview_channel` parity)  
7. `AUTO_PUBLISH_ENABLED` policy reviewed; `make autopublish-status`  
8. Operator commands tested: `/health`, `/runtime`, `/anomalies`, `/lastpub`  
9. Rollback path documented below  

## Verdicts

| Command | READY | CONDITIONAL | NOT_READY |
|---------|-------|-------------|-----------|
| `make public-go-check` | exit 0 | exit 2 | exit 1 |
| `make release-readiness` | exit 0 | exit 2 | exit 1 |

## PREPUBLIC_QA_MODE

```bash
PREPUBLIC_QA_MODE=true
MODERATION_CHAT_ID=<private QA chat>
```

Writes `var/runtime/prepublic_validation_report.json` on heartbeat and mirrors publishes to QA chat.

## Rollback procedure

1. `GLOBAL_PUBLISH_PAUSE=true` or `/pause_autopublish`  
2. `RUNTIME_OPERATIONAL_MODE=maintenance` if needed  
3. Stop container: `docker compose stop newsroom` (VPS)  
4. Restore DB from backup: `make backup-sqlite` / restore script  
5. Investigate `make incident-report` artifacts  

## Safe pause / resume

```text
/pause_autopublish   # operator flag file — ingest continues
/resume_autopublish  # clears pause; gates still enforced
```

## Controlled public rollout

```bash
CONTROLLED_PUBLIC_ROLLOUT=true
ROLLOUT_STAGE=STAGE_0_PRIVATE_QA
```

Advance: `STAGE_1_LIMITED_PUBLIC` → `STAGE_2_OBSERVED_PUBLIC` → `STAGE_3_FULL_AUTONOMOUS` only after gates pass.

Telegram: `/release_status`, `/go_status`, `/burnin_status`

## Final release gate

```bash
make final-release-check    # writes var/runtime/FINAL_RELEASE_REPORT.json
make chaos-lite-validate    # in-process recovery tests
```

Verdict: `BLOCKED` | `CONDITIONAL` | `APPROVED`

## VPS monitoring (daily)

```bash
make ops-status
make autopublish-status
make operator-health
make final-release-check
make server-burnin   # remote
```

See [PRODUCTION_DEPLOYMENT.md](./PRODUCTION_DEPLOYMENT.md), [INCIDENT_RESPONSE.md](./INCIDENT_RESPONSE.md).
