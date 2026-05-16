# Operational maturity assessment (v3.2)

Assessment of the **offline operational tooling program** at v3.2 FINAL. Separate from production-lite runtime maturity (v3.1).

## Summary grade: **A- (production-lite ops tooling scope)**

Suitable for long-term stewardship with documented limitations.

## Dimension scores

| Dimension | Grade | Notes |
|-----------|-------|-------|
| Governance maturity | A | ADR-030–034, maintenance policy, freeze criteria |
| Operational safety | A | Read-only, no publish/queue mutation |
| Rollback readiness | A | Delete `var/ops_*`; no redeploy required |
| Observability quality | B+ | Counter-delta proxies; not wall-clock Telegram latency |
| Deterministic reproducibility | A | Frozen UTC tests, manifests, checksums |
| Tooling maintainability | A | Layered utils, Makefile gates, contract tests |
| Runtime isolation discipline | A | No publisher/worker changes in tooling program |
| Operator sustainability | B+ | Requires cron discipline for snapshots |

## Known limitations (intentional)

- Publish latency charts are **counter-delta proxies**, not end-to-end Telegram timing.
- Empty `var/ops_history/` on new hosts until first snapshot.
- Legacy snapshots may lack `diagnostics.schema_version` (WARN only).
- Index HTML lists relative paths; moving dirs breaks links until regenerate.
- Release kits capped at 30MB; very large histories need archive-first strategy.

## Intentional non-goals

- Real-time dashboards or alerting platform
- Multi-node centralized metrics
- Auto-remediation or retry automation from analytics
- SaaS telemetry vendors
- In-process runtime tracing hooks

## Future risk boundaries

| Risk | Mitigation |
|------|------------|
| Platform creep | ADR-034 forbidden list; “when NOT to build” stewardship doc |
| Schema drift | `validate_ops_schema.py` + governance contracts |
| Unbounded disk | P1 rotation + P2 archive + kit size cap |
| Runtime coupling | Contract tests; no `publisher` imports in ops tools |
| Stale operator process | Quarterly recovery drill + certification sign-off |

## Validation reference

```bash
make stewardship-validate
```

## Sign-off

| Role | Date |
|------|------|
| Engineering | 2026-05-16 |
| Operator | |
