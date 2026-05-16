# Operational integrity audit (v3.2 P3)

Bounded checklist for offline operational tooling. **Does not** replace production incident response or runtime contract audits.

## Scope

| In scope | Out of scope |
|----------|--------------|
| `var/ops_history`, `var/ops_reports`, `var/ops_archive`, `var/ops_bundle` | `runtime/*.json` contract files |
| P1–P3 tools under `tools/` | Publisher, worker, scheduler |
| Schema validation and export reproducibility | Live Telegram load tests |

## Expected invariants

1. Snapshots are `read_only` with `no_telegram_api_calls` and `no_redis_mutations`.
2. History rotation: ≤200 files and ≤20MB total (P1).
3. Archive files gzip-valid and parse as JSON arrays (P2).
4. Analytics derived only from snapshots; no runtime feedback.
5. Bundle total size ≤30MB (P3 `MAX_BUNDLE_BYTES`).
6. Manifest paths sorted; checksums match files.
7. Corrupt snapshots isolated, not propagated to aggregates.
8. `make ops-bundle-validate` green in CI without network.

## Audit checklist

| # | Check | Method | Pass |
|---|-------|--------|------|
| 1 | Retention enforced | `tests/tools/test_ops_tooling.py` rotate | ☐ |
| 2 | Archive recoverable | `verify_archive_file` + roundtrip test | ☐ |
| 3 | Schema compatibility | `validate_ops_schema.py` on fixtures | ☐ |
| 4 | Reproducible reporting | `test_toolchain_reproducibility.py` | ☐ |
| 5 | Corrupt snapshot handling | corrupt fixture skipped | ☐ |
| 6 | Bounded storage | manifest `total_bytes` cap | ☐ |
| 7 | Deterministic outputs | double export hash match | ☐ |
| 8 | Rollback simplicity | delete `var/ops_*` + stop cron | ☐ |
| 9 | No runtime coupling | grep: no publisher imports in P3 tools | ☐ |
| 10 | Portable HTML | single file, no CDN, opens offline | ☐ |

## Automated verification

```bash
make ops-bundle-validate
make ops-analytics-validate
make ops-tooling-validate
```

## Corruption drill (operator)

1. Copy a valid snapshot; truncate last byte → run `validate_ops_schema.py` → expect `CORRUPT`.
2. Run `ops_analytics_aggregate.py` → corrupt file in `skipped_corrupt`, summary still produced.
3. Export bundle → validation report lists corrupt; healthy files in manifest.

## Rollback

1. Stop scheduled ops snapshot jobs.
2. Remove `var/ops_bundle/` and regenerated `var/ops_reports/` if needed.
3. Keep `var/ops_history/` unless disk pressure requires archive-only retention.
4. No application redeploy required for tooling rollback.

## Operator sign-off

| Role | Name | Date | Notes |
|------|------|------|-------|
| Operator on-call | | | |
| Engineering | | | |

**Audit result:** ☐ PASS ☐ PASS WITH WARNINGS ☐ FAIL
