# Drill: invalid schema_version

**Cause:** `health_snapshot.json` has `"schema_version": 2`.

**Run:**

```bash
python3 -m newsroom.cli check-compatibility --path . --strict
```

**Expected:**

- `compatibility_status: FAIL`
- `compatibility_warnings: health_snapshot.json:future_schema_version:2`

**Recovery:** Re-run nightly or set `schema_version` back to `1` and regenerate reports.
