# Feature freeze — stability mode only

**Status: ACTIVE**  
**Effective: pre–controlled public launch burn-in**

## SYSTEM IS IN STABILITY MODE ONLY

The Telegram AI newsroom is frozen for feature development until burn-in completes and controlled public launch is approved.

### Forbidden until launch

- New agents, pipelines, or orchestration redesigns
- New AI capabilities (summarizers, ranking, scoring systems)
- New experimental modules or feature flags without expiry
- Editorial “experiments” that change production behavior without ops review

### Allowed changes only

| Category | Examples |
|----------|----------|
| Bug fixes | Crashes, incorrect terminal states, duplicate publish |
| Stability | Stuck ticks, scheduler gaps, idempotency, stale recovery |
| Observability | Metrics, health endpoints, `stability-report`, runbooks |
| Operational safeguards | `GLOBAL_PUBLISH_PAUSE`, runtime control modes, publish audit |

### Degradation model (frozen to three tiers)

Summarization and runtime behavior map to **three** fallback tiers only:

1. **Normal** — primary OpenAI path when available  
2. **Degraded** — rule/structured fallback (`BURNIN_OPENAI_ALWAYS_FALLBACK`, circuit open)  
3. **Text-only** — publish without media enrichment (`TEXT_ONLY` control mode or `MEDIA_PIPELINE_ENABLED=false`)

Operator-facing modes (persisted, logged): `NORMAL`, `SOFT_DEGRADED`, `HARD_DEGRADED`, `TEXT_ONLY`, `PAUSED`.  
See `app/ops/runtime_control.py` and `docs/ARCHITECTURE_FREEZE.md`.

### Burn-in success (public readiness)

- 3–7 days uninterrupted VPS uptime  
- `make burnin-check` → PASS  
- `make stability-report` → acceptable `system_stability_score`  
- `make public-go-check` → PASS  
- Zero stuck `running` ticks, zero duplicate channel posts  
- Restart recovery and non-blocking media verified  

### Execution model

See [PIPELINE_EXECUTION.md](./PIPELINE_EXECUTION.md) — linear tick flow, single finalizer, unified gates.

### Related docs

- [ARCHITECTURE_FREEZE.md](./ARCHITECTURE_FREEZE.md) — no structural changes  
- [PHASE3_STABILITY_FREEZE.md](./PHASE3_STABILITY_FREEZE.md) — phase 3 deliverables  
- [TECHNICAL_DEBT_FREEZE.md](./TECHNICAL_DEBT_FREEZE.md) — debt audit  
- [BURN_IN_VALIDATION.md](./BURN_IN_VALIDATION.md) — tick/log contract checks  
- [PREPUBLIC_CHECKLIST.md](./PREPUBLIC_CHECKLIST.md) — launch checklist  

### Commands

```bash
make reliability-test
make burnin-check
make stability-report
make public-go-check
```

**If nothing interesting happens for 48 hours, the system is healthy.**
