# Reproducible runtime workflow

What should match across runs vs what may differ. See [REPRODUCIBILITY.md](../REPRODUCIBILITY.md).

## Steps

```bash
export OUTPUT_DIR=./runtime_ops_output
export RUNTIME_DIR=./var/runtime

# 1) Generate artifacts (inputs may vary)
make runtime-nightly RUNTIME_DIR="$RUNTIME_DIR" OUTPUT_DIR="$OUTPUT_DIR"

# 2) Catalog — structure is reproducible; timestamps are not
make runtime-index OUTPUT_DIR="$OUTPUT_DIR"

# 3) Checksums — reproducible given same files on disk
make verify-runtime OUTPUT_DIR="$OUTPUT_DIR"

# 4) Baseline — duration comparison (approximate threshold)
make create-baseline OUTPUT_DIR="$OUTPUT_DIR"
make compare-baseline OUTPUT_DIR="$OUTPUT_DIR"

# 5) Contract validation (fully reproducible in CI)
make contracts
```

## Should match (same inputs on disk)

| Check | Stable across runs |
|-------|-------------------|
| `runtime-index` artifact list & lifecycle order | Yes |
| `verify-runtime` checksum results | Yes, if files unchanged |
| `check-compatibility` schema_version classification | Yes |
| `make contracts` | Yes (CI) |
| ZIP bundle hash | Yes, if `RUNTIME_STATE_DIR` snapshot identical |

## May differ

| Field | Reason |
|-------|--------|
| `generated_at` | Wall clock |
| `runtime_duration_sec` | Load, soak timing |
| OpenAI/cluster content | Nondeterministic model |
| Benchmark counters | Live pipeline activity |
| `compare-baseline` WARNING | Duration drift > 15s |

## Identical contract validation

```bash
make contracts
# or full CI slice:
make ci-test
```

Contract tests do not call OpenAI or Telegram. They validate frozen filenames, enums, docs links, and Makefile help sections.

## Strict operator gate

```bash
python -m newsroom.cli runtime-index --path "$OUTPUT_DIR" --strict
python -m newsroom.cli verify-runtime --path "$OUTPUT_DIR" --strict
```

Exit code `1` on `WARNING` or `FAIL` — reproducible policy, not reproducible timestamps.

## Related

- [../DEMO_WALKTHROUGH.md](../DEMO_WALKTHROUGH.md)
- [../../examples/runtime_samples/](../../examples/runtime_samples/)
