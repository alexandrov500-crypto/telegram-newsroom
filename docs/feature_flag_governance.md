# Feature flag governance

Environment-driven behavior flags (not a dynamic flag service).

## Flag classes

| Class | Default | Promotion |
|-------|---------|-----------|
| **Core** | Documented in `.env.example` | Stable at install |
| **Reliability (opt-in)** | `false` | Minor + validation |
| **Experimental** | `false` | Not for production default-on |
| **Diagnostic** | `false` | Maintainer-only |

## Registered reliability flags (v1.1–v1.3)

| Env var | Since | Class | Purpose |
|---------|-------|-------|---------|
| `WORKER_RETRY_SAFE` | v1.1 | Reliability | Enqueue before ack on retry |
| `PUBLISH_LOCK_STRICT` | v1.1 | Reliability | Fail closed if Redis lock unavailable |
| `RUNTIME_DRIFT_MONITOR` | v1.3 | Diagnostic | Drift reports (no behavior change alone) |
| `SCHEDULER_DIAGNOSTICS` | v1.3 | Diagnostic | Scheduler run ring buffer |
| `SECURITY_REDACTION` | v1.6 | Reliability | Deterministic secret masking in logs/DLQ |

Verified by `tools/release_readiness.py` and `tools/security_readiness.py` against code registry.

## Experimental flags lifecycle

1. Document in CHANGELOG `[Experimental]`
2. Default off ≥ 1 minor release
3. Chaos/soak coverage before stable promotion
4. Deprecation per [deprecation_policy.md](deprecation_policy.md)

## Default-enable criteria

To flip default to `true` in code/env example:

- ADR or minor release note
- No frozen contract impact
- Rollback documented
- Multi-worker safety reviewed for lock/retry flags

## Rollback expectations

- Revert env var → prior behavior immediately after process restart
- No migration required for opt-in flags

## Incompatible flag combinations

| Combination | Risk | Guidance |
|-------------|------|----------|
| `PUBLISH_LOCK_STRICT=1` + `REDIS_ENABLED=0` + multi-worker | Publish blocked or inconsistent | Single worker only, or enable Redis |
| `WORKER_RETRY_SAFE=0` + high retry storm | Job loss edge case | Enable safe retry under load |

Readiness tool warns on active env combos when `--check-env` passed.

## Observability requirements

Flags that change behavior MUST:

- Appear in `config_fingerprint()` when drift monitor used
- Be listed in [deploy/example.env.production-lite](../deploy/example.env.production-lite) comments
- Have runbook if operator-visible failure mode

## Related

- [compatibility_policy.md](compatibility_policy.md) · [runbooks/upgrades/EXPERIMENTAL_FLAG_ENABLE.md](runbooks/upgrades/EXPERIMENTAL_FLAG_ENABLE.md)
