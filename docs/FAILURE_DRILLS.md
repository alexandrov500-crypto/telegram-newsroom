# Failure drills (v1.0.0)

Read-only scenarios using **existing** inspection CLIs. Fixtures: [examples/failure_drills/](../examples/failure_drills/).

## How to run a drill

```bash
export DRILL=examples/failure_drills/broken_checksum
python3 -m newsroom.cli verify-runtime --path "$DRILL"
python3 -m newsroom.cli validate-recovery --path "$DRILL"
python3 -m newsroom.cli check-compatibility --path "$DRILL"
python3 -m newsroom.cli runtime-index --path "$DRILL"
```

Append `--strict` to exercise CI exit codes.

## Scenarios

| Drill | Simulates | Expected | Recovery path |
|-------|-----------|----------|-----------------|
| [broken_checksum](../examples/failure_drills/broken_checksum/) | Corrupted manifest / tampered file | `verify-runtime` **FAIL**, checksum_mismatches | Re-run nightly or `make runtime-manifest` after fixing files |
| [missing_required](../examples/failure_drills/missing_required/) | Incomplete nightly | `runtime-index` **FAIL**, many missing | `make runtime-nightly` |
| [invalid_schema](../examples/failure_drills/invalid_schema/) | Wrong schema_version | `check-compatibility` **FAIL** | Fix JSON or regenerate artifacts |
| [warning_optional_missing](../examples/failure_drills/warning_optional_missing/) | No baseline/drift | `runtime-index` **WARNING** | `make create-baseline` if drift needed |
| [missing_bundle](../examples/failure_drills/missing_bundle/) | No `runtime_bundle.zip` | `validate-recovery` **WARNING**, missing_optional:runtime_bundle.zip | Re-run nightly bundle step |

## missing runtime_bundle.zip (live)

If `runtime_bundle.zip` absent at `OUTPUT_DIR` root but `runtime/` looks complete:

- `validate-recovery` → WARNING `missing_optional:runtime_bundle.zip`
- `replay-runtime` cannot extract — expected
- **Recovery:** `make runtime-nightly` or restore snapshot / backup

## corrupted manifest

Manual edit or partial copy → `verify-runtime` **FAIL** with `checksum_mismatches` or `missing_required`.

**Recovery:** `make runtime-manifest OUTPUT_DIR=...` only if files on disk are correct; otherwise re-run nightly.

## checksum mismatch

See `broken_checksum` drill. **Do not** use `examples/runtime_samples/` for verify — placeholder hashes.

## missing required artifact

See `missing_required` drill. Index lists `(missing)` per lifecycle step.

## invalid schema_version

See `invalid_schema` drill. `compatibility_warnings: … future_schema_version:2` or failures on missing version fields.

## Operator rules

- Inspection tools **do not repair** artifacts.
- Prefer `make runtime-nightly` over hand-editing JSON.
- Use `scripts/runtime_sanity_check.sh` after incidents.

## Related

- [RESTORE_PROCEDURE.md](RESTORE_PROCEDURE.md) · [OPERATOR_QUICKSTART.md](OPERATOR_QUICKSTART.md)
