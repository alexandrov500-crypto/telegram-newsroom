# Incident response

## Severity levels

| Level | Signal | Action |
|-------|--------|--------|
| WARNING | elevated runtime, retry spikes | Monitor; `make stability-report` |
| CRITICAL | runtime protection, execution graph, public incident freeze | **Pause auto**; diagnose before resume |

## CRITICAL workflow (public-safe)

The system **never** silently continues a corrupted publish flow.

1. **Autonomous publish frozen** — `public_incident_state.json`, operator pause file
2. **Diagnostics preserved** — `var/runtime/incident_diagnostics/critical_*.json`
3. **Operator notified** — Telegram admin chat via pending notifications
4. **Restart loop guard** — repeated CRITICAL within 30m blocks unsafe auto-resume

### Operator emergency actions

```text
/pause_autopublish
/runtime_state
/last_alerts
/recent_failures
/continuity
```

On VPS:

```bash
make incident-report
make autopublish-status
journalctl -u newsroom -n 200 --no-pager
```

### Resume (only when root cause fixed)

```text
/resume_autopublish
```

Clears operator pause and incident freeze. Publish gates and execution graph still apply.

## Telegram failures

See `docs/runbooks/production/TELEGRAM_FAILURE_RUNBOOK.md`.

- FloodWait burst → collector/publisher backoff; check `telegram_production_state.json`
- Channel access lost → verify bot admin on target channel
- Repeated publish failures → `make ops-status`; do not delete pending drafts blindly

## OpenAI cascade

- Runtime protection escalates to DEGRADED/CRITICAL
- Summarize fallback path continues where configured
- `GLOBAL_PUBLISH_PAUSE` if manual control needed

## Never do

- Auto-delete pending publishes on CRITICAL
- Force-clear `execution_graph_safety.json` without understanding corrupted ticks
- Run two processes with same `BOT_TOKEN` (Mac + VPS)

## Post-incident

1. `make final-release-check`
2. Update burn-in snapshot: `make burnin-check`
3. Document in operator log; advance rollout stage only when stable
