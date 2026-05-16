# Demo walkthrough (production-lite operations)

Demo-ready narrative for operators and reviewers. Uses sanitized samples in [examples/runtime_samples/](../examples/runtime_samples/) when you cannot run a live nightly.

**Prerequisites:** `make install-dev`, writable `OUTPUT_DIR` (default `./runtime_ops_output`).

## Scenario overview

Demonstrate end-to-end operational maturity without platform-scale tooling:

1. Nightly run  
2. Runtime index  
3. Verification  
4. Recovery validation  
5. Compatibility check  
6. Audit inspection  
7. Baseline compare  

## 1. Nightly run

```bash
export OUTPUT_DIR=./runtime_ops_output
make runtime-nightly RUNTIME_DIR=./var/runtime OUTPUT_DIR="$OUTPUT_DIR"
```

**Expected:** exit code `0`; `$OUTPUT_DIR/runtime/` populated; last file `runtime_index.json`.

**Demo without live run:** point reviewers at `examples/runtime_samples/` and explain the same lifecycle order.

## 2. Runtime index

```bash
make runtime-index OUTPUT_DIR="$OUTPUT_DIR"
# or JSON:
python -m newsroom.cli runtime-index --path "$OUTPUT_DIR" --json
```

**Expected:** `index_status` = `OK`, `runtime_model` = `single-node`, `artifact_count` = 14.

Sample excerpt (`examples/runtime_samples/runtime_index.json`):

```json
{
  "index_status": "OK",
  "runtime_model": "single-node",
  "artifact_count": 14
}
```

## 3. Verification

```bash
make verify-runtime OUTPUT_DIR="$OUTPUT_DIR"
```

**Expected:** manifest checksums match on-disk files; `verification_status` = `OK`.

## 4. Recovery validation

```bash
make validate-recovery OUTPUT_DIR="$OUTPUT_DIR"
make replay-runtime OUTPUT_DIR="$OUTPUT_DIR"
```

**Expected:** `recovery_status` = `OK`; replay extracts bundle to a temp dir (read-only inspection).

See [examples/recovery_validation_example.md](examples/recovery_validation_example.md).

## 5. Compatibility check

```bash
make check-compatibility OUTPUT_DIR="$OUTPUT_DIR"
```

**Expected:** all artifacts `schema_version: 1`; `compatibility_status` = `OK`.

## 6. Audit inspection

```bash
make audit-runtime OUTPUT_DIR="$OUTPUT_DIR"
```

**Expected:** bounded `qualification_history.json` (≤20 entries) and `audit_snapshot.json` with `audit_status` = `OK`.

## 7. Baseline compare

```bash
make create-baseline OUTPUT_DIR="$OUTPUT_DIR"
make compare-baseline OUTPUT_DIR="$OUTPUT_DIR"
```

**Expected (first run):** baseline created; drift `OK` or `WARNING` if duration exceeds threshold (15s).

See [examples/drift_detection_example.md](examples/drift_detection_example.md).

## Strict demo gate (release-style)

```bash
python -m newsroom.cli runtime-index --path "$OUTPUT_DIR" --strict
python -m newsroom.cli verify-runtime --path "$OUTPUT_DIR" --strict
python -m newsroom.cli inspect-policy --path "$OUTPUT_DIR" --strict
```

Any `WARNING` or `FAIL` exits non-zero with `--strict`.

## Narrative closing

- Governance model is **complete** — inspection only, no enforcement daemons.
- Contracts are frozen — see [architecture/RUNTIME_CONTRACTS.md](architecture/RUNTIME_CONTRACTS.md).
- This project optimizes for **operational simplicity** over platform-scale extensibility.
