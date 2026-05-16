# Example: drift detection (baseline)

Compares current nightly metrics against a saved baseline. **Experimental** until `create-baseline` has been run at least once.

## CLI sequence

```bash
export OUTPUT_DIR=./runtime_ops_output

# Establish baseline after a known-good nightly
make create-baseline OUTPUT_DIR="$OUTPUT_DIR"

# Later nightly — compare
make compare-baseline OUTPUT_DIR="$OUTPUT_DIR"
python -m newsroom.cli compare-baseline --path "$OUTPUT_DIR" --json
```

## Expected outputs

| Situation | `drift_status` | Meaning |
|-----------|----------------|---------|
| No baseline file yet | `WARNING` | `compare-baseline` before `create-baseline` |
| Duration within threshold | `OK` | Within 15s warning threshold |
| Duration spike | `WARNING` | `runtime_duration_sec` drift |
| Corrupt baseline JSON | `FAIL` | Unreadable baseline |

## Incident reasoning

1. Run `make runtime-health` — confirm `runtime_duration_sec` in snapshot.
2. If drift WARNING only — investigate soak/benchmark load, not schema breakage.
3. Re-baseline only after intentional config change (document why in operator log).

## Strict gate

```bash
python -m newsroom.cli compare-baseline --path "$OUTPUT_DIR" --strict
```

## Related

- [DEMO_WALKTHROUGH.md](../DEMO_WALKTHROUGH.md) step 7
- [architecture/ADR-011-runtime-baseline-and-drift-semantics.md](../architecture/ADR-011-runtime-baseline-and-drift-semantics.md)
