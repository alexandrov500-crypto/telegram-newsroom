# EVIDENCE_RETENTION

## Detection

- `OUTPUT_DIR` / `ci-artifacts` disk full
- Drift `evidence_growth` warnings

## Mitigation

```bash
python3 tools/evidence_retention.py report --output-dir ./runtime_ops_output
python3 tools/evidence_retention.py prune --artifacts-dir ./ci-artifacts --max-count 32 --dry-run
```

Remove dry-run when satisfied.

## Safe restart

Prune does not touch live `RUNTIME_STATE_DIR` unless paths overlap.

## Validation

`evidence_retention.py verify-manifest --output-dir …`

## Rollback

Restore pruned zips from offline backup if wrongly deleted.

## Evidence collection

- Retention JSON report
- `runtime_manifest.json` checksum status

## Escalation thresholds

- Evidence > 50GB → define operator archive policy
