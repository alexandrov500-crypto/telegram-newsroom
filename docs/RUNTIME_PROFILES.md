# Runtime profiles

The newsroom operator can run in three runtime profiles. Set:

```bash
RUNTIME_PROFILE=minimal_pilot   # controlled Telegram pilot (default when LIVE_MODE=canary)
RUNTIME_PROFILE=standard_live   # production-style ops without full research stack
RUNTIME_PROFILE=research_full   # full cognitive / mesh / epistemic orchestration
```

If `RUNTIME_PROFILE` is unset, **canary** or **APP_ENV=pilot** selects `minimal_pilot`.

## minimal_pilot

**Use when:** controlled public pilot, canary publishing, operator-supervised live ops.

**Goal:** stable Telegram operator responsiveness and safe publishing — not experimental cognition.

### Active

- Telegram operator (polling, commands, approvals)
- `controlled_live` — canary caps, freeze, rollback, publish trace, quarantine
- RSS ingestion (rate-limited, async fetch, timeouts)
- Health watchdog + soft-degrade on lag
- Optional production safety + reliability (lightweight)

### Passive

- `autonomous-runtime` — heartbeat only, no recovery storms (120s+ interval)

### Disabled

- `cognitive-runtime`, `federated-cognitive-mesh`, `epistemic-integrity`
- `operator-signal-hub` (no digest/scoring pressure)
- Full `operations-platform` tick (replaced by `pilot-ops` every 120s)
- Research stacks: live_ops, ops_cert, ga_ops, opmem, week1, etc.
- Digest / analytics / Telethon ingest schedulers
- Cluster coordinator

### Resource expectations

- Low CPU; event loop should stay responsive
- Background tasks target ≤10 concurrent loops
- No recurring stalled-loop alerts under normal RSS load

## standard_live

**Use when:** production channel with full ops playbook but without research mesh.

- Operations platform tick (180s)
- Live ops, certification, playbook, live deploy
- Operator signal hub active
- Research cognitive layers **off**

## research_full

**Use when:** staging burn-in, federation experiments, epistemic/mesh development.

Enables all loops and coordinator stacks. **Not** appropriate for pilot canary.

## Operational tradeoffs

| Profile | Operator UX | Publish safety | CPU / lag risk |
|---------|-------------|----------------|----------------|
| minimal_pilot | Best | High (controlled_live) | Lowest |
| standard_live | Good | High | Medium |
| research_full | Can degrade under load | Depends on config | Highest |

## Startup visibility

On boot, `minimal_pilot` logs `event=runtime_profile_*` lines and sends an HTML summary to the ops channel (with the pilot banner).

HTTP: `GET /runtime_performance` includes `soft_degraded` and loop health.

## Related docs

- [RUNTIME_PERFORMANCE.md](RUNTIME_PERFORMANCE.md) — lag diagnostics, RSS/async rules
- [PILOT_ACTIVATION.md](PILOT_ACTIVATION.md) — channel setup and canary policy
