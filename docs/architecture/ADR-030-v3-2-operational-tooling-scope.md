# ADR-030: v3.2 operational tooling scope

**Status:** Accepted  
**Date:** 2026-05-16  
**Context:** v3.2 planning gate; stabilization freeze; production-lite grade A.

## Decision

Implement **P1 read-only operational tooling** only:

- Metrics history snapshots (`tools/ops_metrics_snapshot.py`)
- Queue introspection (`tools/queue_introspection.py`)
- Publish timeline reporting (`tools/publish_timeline_report.py`)
- Operator shift checklist (docs)

No changes to publish pipeline, retry semantics, queue transport, scheduler, or locking.

## Allowed

| Area | Examples |
|------|----------|
| Diagnostics aggregation | Wrap `live_telegram_diagnostics` |
| Metrics history | `var/ops_history/*.json`, rotation |
| Read-only queue inspection | LLEN, SCAN, LINDEX — no dequeue |
| Timeline reporting | Offline snapshot + `operational_timeline.json` |
| Retry analytics | Counter deltas from snapshots |
| Operator reporting | Markdown/JSON exports |
| Docs / runbooks / contract tests | ADR, exit criteria |

## Forbidden

- Autonomous remediation
- Retry orchestration or model changes
- Publish scheduling / cadence code changes
- Moderation automation
- Multi-worker coordination redesign
- Queue rewrites, event bus implementation
- New background workers
- Default-on network exporters

## Architectural constraints

1. **Read-only:** tools set `read_only: true`; no Telegram API calls; no Redis writes.
2. **Bounded storage:** max 200 files / 20MB under `var/ops_history` (configurable flags).
3. **Schema version:** `OPS_SNAPSHOT_SCHEMA_VERSION = 1` in `utils/ops_tooling.py`.
4. **Frozen runtime contracts:** no new `runtime/*.json` artifacts.
5. **Publish path untouched:** no edits to `publisher/`, `publish_service`, locks, or `collector/retry.py` behavior.

## Rollback guarantees

- Remove tools or stop cron — no runtime state change
- Delete `var/ops_history/` safely
- Revert git commit — zero DB migration

## Operational safety rules

- Run snapshots as operator user; redact logs per `SECURITY_REDACTION`
- `--strict` verify before shift; not a substitute for incident runbooks
- Queue introspection may show stale counts — never use for automated actions

## CI determinism requirements

- Unit tests use `tmp_path` fixtures only
- No live Telegram, no live Redis in CI (mocks/fakes)
- `make ops-tooling-validate` required on PRs touching `tools/ops_*`, `utils/ops_tooling.py`, `utils/queue_introspection.py`

## Consequences

- Improved visibility without production risk
- v3.2 P2+ items (OTel, event bus) remain design-only per [v3_2_discovery.md](v3_2_discovery.md)

## References

- [v3_2_p1_exit_criteria.md](../releases/v3_2_p1_exit_criteria.md)
- [stabilization_freeze_policy.md](../governance/stabilization_freeze_policy.md)
