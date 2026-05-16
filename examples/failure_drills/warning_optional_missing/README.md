# Drill: optional artifacts missing

**Cause:** All required runtime JSON present; `runtime_baseline.json` and `drift_report.json` absent.

**Run:**

```bash
python3 -m newsroom.cli runtime-index --path . --strict
```

**Expected:**

- `index_status: WARNING` (optional baseline/drift not present)

**Recovery:** `make create-baseline OUTPUT_DIR=…` when drift tracking is desired.
