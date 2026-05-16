# v3.2 P1 exit criteria

P1 operational tooling is **complete** only when all criteria below are met.

## Implementation scope (ADR-030)

| Deliverable | Required |
|-------------|----------|
| `tools/ops_metrics_snapshot.py` | ☑ |
| `tools/queue_introspection.py` | ☑ |
| `tools/publish_timeline_report.py` | ☑ |
| ADR-030 + ops docs | ☑ |
| `make ops-tooling-validate` green | ☑ |

## Quality gates

| # | Criterion | Verification |
|---|-----------|--------------|
| 1 | Tooling strictly read-only | ADR-030; no Redis/Telegram writes in code review | ☑ |
| 2 | No runtime semantic drift | No changes to publisher/retry/scheduler/lock | ☑ |
| 3 | Contracts backward compatible | `make ci-test`; frozen runtime tests pass | ☑ |
| 4 | CI deterministic | No live services in ops tooling tests | ☑ |
| 5 | Rollback trivial | Delete tools + history dir | ☑ |
| 6 | Bounded storage confirmed | Rotation tests; max files/bytes | ☑ |
| 7 | Operator workflow improved | Shift checklist adopted | ☑ |
| 8 | Production safeguards untouched | `production_safeguards.md` audit unchanged | ☑ |

## Validation commands

```bash
make ops-tooling-validate
make ci-test
make governance-validate
```

## Sign-off

| Role | Date | Signature |
|------|------|-----------|
| Operator | | |
| Engineering | | |

**P1 status:** ☑ COMPLETE (engineering) — operator sign-off optional
