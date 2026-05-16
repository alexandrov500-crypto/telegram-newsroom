# Release checklist (production-lite)

Use before tagging or promoting a build. **No new governance layers** — validate frozen contracts.

## 1. Automated tests

```bash
make ci-test          # runtime + smoke + contract tests
# optional: make ci-nightly && make ci-release-check
```

**Required:** all tests pass.

## 2. Runtime verification (offline)

Set `OUTPUT_DIR` to a fresh or known-good nightly output.

```bash
make runtime-index OUTPUT_DIR=./runtime_ops_output
make verify-runtime OUTPUT_DIR=./runtime_ops_output
make validate-recovery OUTPUT_DIR=./runtime_ops_output
make check-compatibility OUTPUT_DIR=./runtime_ops_output
make inspect-policy OUTPUT_DIR=./runtime_ops_output
make inspect-capabilities OUTPUT_DIR=./runtime_ops_output
```

### Release readiness criteria

| Check | Expected |
|-------|----------|
| Smoke + contract tests | pass |
| `runtime_index` → `index_status` | `OK` (or documented `WARNING`) |
| `verify-runtime` → `verification_status` | `OK` |
| `recovery_report` → `recovery_status` | `OK` |
| `compatibility_report` → `compatibility_status` | `OK` |
| `policy_report` → `policy_validation_status` | `OK` |
| Checksums | `checksum_mismatches` empty |
| Required artifacts | no gaps in `runtime_index` |
| Deterministic ZIP | `tests/runtime/test_runtime_bundle.py` ordering (CI) |

Strict gate example:

```bash
python -m newsroom.cli runtime-index --path "$OUTPUT_DIR" --strict
python -m newsroom.cli verify-runtime --path "$OUTPUT_DIR" --strict
python -m newsroom.cli validate-recovery --path "$OUTPUT_DIR" --strict
python -m newsroom.cli check-compatibility --path "$OUTPUT_DIR" --strict
python -m newsroom.cli inspect-policy --path "$OUTPUT_DIR" --strict
```

## 3. Baseline compare (optional)

If release baseline exists:

```bash
make compare-baseline OUTPUT_DIR=./runtime_ops_output
# expect drift_status OK or documented WARNING
```

## 4. Documentation

- [OPERATOR_QUICKSTART.md](OPERATOR_QUICKSTART.md) reflects current CLI names.
- [RUNTIME_CONTRACTS.md](architecture/RUNTIME_CONTRACTS.md) unchanged or version bump noted.

## 5. Sign-off

- [ ] `make ci-test` green  
- [ ] `runtime_index` strict OK  
- [ ] verification + recovery + compatibility + policy strict OK  
- [ ] No required artifact gaps  
- [ ] No checksum mismatches  
- [ ] Release notes mention contract version (`schema_version: 1`)
