# Example: recovery validation

Validates that `runtime_bundle.zip` is structurally recoverable (offline, read-only).

## Prerequisites

- Nightly completed with bundle step OK
- `$OUTPUT_DIR/runtime_bundle.zip` exists

## CLI sequence

```bash
export OUTPUT_DIR=./runtime_ops_output

# Write/update recovery_report.json
make validate-recovery OUTPUT_DIR="$OUTPUT_DIR"

# Optional: extract bundle to temp dir for inspection
make replay-runtime OUTPUT_DIR="$OUTPUT_DIR"
```

JSON inspection:

```bash
python -m newsroom.cli validate-recovery --path "$OUTPUT_DIR" --json
```

## Expected output (OK)

```json
{
  "recovery_status": "OK",
  "bundle_present": true,
  "extract_ok": true
}
```

(Field names may include additional metadata per `recovery_report.json` schema v1.)

## Failure scenarios

| `recovery_status` | Likely cause |
|-------------------|--------------|
| `FAIL` | Missing or corrupt `runtime_bundle.zip` |
| `FAIL` | Zip truncated during copy |
| `WARNING` | Bundle present but optional members missing |

**Reasoning:** recovery validates **artifact portability**, not live DB restore. DB restore uses `backup_cli` separately.

## Strict gate

```bash
python -m newsroom.cli validate-recovery --path "$OUTPUT_DIR" --strict
```

## Related

- [runtime_failure_investigation.md](runtime_failure_investigation.md)
- [BACKUP_AND_RECOVERY.md](../BACKUP_AND_RECOVERY.md)
