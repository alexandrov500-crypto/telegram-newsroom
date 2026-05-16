# Drill: missing required artifacts

**Cause:** Only `runtime_report.json` present under `runtime/`.

**Run:**

```bash
python3 -m newsroom.cli runtime-index --path . --strict
```

**Expected:**

- `index_status: FAIL`
- Most lifecycle steps show `(missing)`

**Recovery:** `make runtime-nightly RUNTIME_DIR=./var/runtime OUTPUT_DIR=…`
