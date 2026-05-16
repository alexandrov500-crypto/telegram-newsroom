# Technical debt registry

Living registry for v3.1 production-lite. **Registry ≠ backlog approval** — changes require ADR + freeze policy check.

| ID | Category | Summary | Severity | Operational impact | Workaround | Recommended fix | Defer justification |
|----|----------|---------|----------|-------------------|------------|-----------------|---------------------|
| TD-101 | runtime | No distributed TX Telegram↔SQLite | HIGH | `FINALIZE_MISMATCH` possible | Manual reconcile | Reconcile tooling (v3.2 read-only) | Architectural; v3.2 design only |
| TD-102 | runtime | Partial multi-chunk publish | MEDIUM | Orphan channel messages | Channel inspect | Document + reconcile tool | No silent auto-delete |
| TD-103 | runtime | Publish lock TTL 180s | MEDIUM | Rare duplicate if hang | Single worker T1 | Tune TTL with ADR | Risky without measurement |
| TD-104 | Telegram | 2FA session not automated | MEDIUM | Collector stop | Re-auth runbook | Out of MVP scope | Platform constraint |
| TD-105 | Telegram | FloodWait not in unified metric until v3.1 | LOW | Log scraping | `telethon_flood_waits` | Done v3.1 | Closed |
| TD-201 | observability | Metrics in-memory only | MEDIUM | Lost on restart | Diagnostics + logs | Scheduled snapshot export | v3.2 candidate |
| TD-202 | observability | No Prometheus default | LOW | Manual diagnostics | `live_telegram_diagnostics` | Opt-in exporter | Philosophy freeze |
| TD-203 | observability | Publish duration not in diagnostics JSON | LOW | Log grep | `publish.telegram_chunks_duration_sec` | Add histogram to export | v3.2 tooling |
| TD-301 | operational | Daily publish cap not env-key | MEDIUM | Operator policy | ≤5/day discipline | Burst window config | Intentional governance |
| TD-302 | operational | Moderation latency not metricized | LOW | Qualitative | Operator notes | Dashboard/API deferred | v3.2 discovery |
| TD-303 | operational | DLQ visibility fragmented | MEDIUM | Operator training | Runbooks | Queue inspect tool | v3.2 candidate |
| TD-401 | testing | Live Telegram not in CI | LOW | Staging only | Mocked `tests/live` | Opt-in staging | By design |
| TD-402 | testing | 24h session soak manual | MEDIUM | External supervisor | Checklist | Soak harness extension | Not blocking T1 |
| TD-501 | deployment | No automated deploy bot | LOW | Manual compose/systemd | DEPLOYMENT_QUICKSTART | Stay manual | production-lite philosophy |
| TD-502 | deployment | Config drift across hosts | MEDIUM | `staging_environment_verify` | Profile + verify CLI | Drift monitor existing | Operator discipline |

## Category definitions

| Category | Scope |
|----------|-------|
| **runtime** | Core pipeline semantics, locks, DB |
| **observability** | Metrics, diagnostics, logs |
| **operational** | Operator toil, runbooks gaps |
| **testing** | Coverage and soak gaps |
| **deployment** | Host, env, release process |
| **Telegram platform** | API/session limits outside code |

## Severity

| Level | Meaning |
|-------|---------|
| CRITICAL | Data loss / duplicate publish / auth breach — fix now (hotfix) |
| HIGH | Steady-state risk with workaround |
| MEDIUM | Toil or occasional incident |
| LOW | Documented acceptable |

## Review cadence

- **72h window:** no new debt items closed without measurement
- **Post-72h:** quarterly review with governance audit
- **v3.2 planning:** only P1 items with gate passed

## Related

- [technical_debt_governance.md](technical_debt_governance.md)
- [v3_2_discovery.md](v3_2_discovery.md)
- [postmortem_template.md](../operations/postmortem_template.md)
