# Drill: broken checksum

**Cause:** `runtime_manifest.json` lists `sha256` of all zeros for `health_snapshot.json`.

**Run:**

```bash
python3 -m newsroom.cli verify-runtime --path . --strict
```

**Expected:**

- `verification_status: FAIL`
- `checksum_mismatches: health_snapshot.json:expected=0000… actual=…`
- Operator actions footer

**Recovery:** `make runtime-nightly` or fix files then `make runtime-manifest OUTPUT_DIR=…`
