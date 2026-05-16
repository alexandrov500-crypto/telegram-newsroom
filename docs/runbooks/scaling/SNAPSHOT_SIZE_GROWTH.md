# SNAPSHOT_SIZE_GROWTH

## Detection

- `OUTPUT_DIR` / `runtime/` subtree > 100 MB warning in diagnostics
- Restore drills exceed expected duration
- Disk usage alerts on inspection volume

## Mitigation

1. Run `tools/evidence_retention.py` / `tools/runtime_retention.py` per policy
2. Archive old nightly outputs off-node
3. Prune redundant drill artifacts

## Safe scaling guidance

- Scaling workers does not reduce snapshot size — retention does
- Plan maintenance window before large restore drills

## Rollback

- Restore from older smaller baseline if prune too aggressive (compare-baseline)

## Evidence collection

- Directory byte counts before/after prune
- Restore drill timing notes

## Escalation thresholds

| Size | Action |
|------|--------|
| > 500 MB OUTPUT_DIR | Mandatory retention pass |
| Restore > SLA window | Change snapshot frequency |
| Contract artifact missing after prune | STOP — compatibility incident |
