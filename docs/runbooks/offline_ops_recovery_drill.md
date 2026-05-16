# Offline ops recovery drill

**Purpose:** Verify operational artifacts can be rebuilt without network, Telegram, or Redis.  
**Duration:** ~15 minutes. **Frequency:** Quarterly or after tooling upgrade.

## Prerequisites

- Repository checkout with Python 3.11+
- Fixture or production snapshot copy under `var/ops_history/` (optional archive under `var/ops_archive/`)

## Drill steps

### 1. Restore reports from archives (if active history empty)

```bash
# Verify archives
python3 tools/ops_archive.py --verify-only --archive-dir var/ops_archive

# Extract is manual: gunzip -c var/ops_archive/YYYY-MM/ops_metrics_*.json.gz > var/ops_history/
# Or re-capture: python3 tools/ops_metrics_snapshot.py --rotate
```

**Pass:** At least one valid `ops_metrics_*.json` in history or documented skip.

### 2. Rebuild analytics from snapshots

```bash
python3 tools/ops_analytics_aggregate.py --history-dir var/ops_history --reports-dir var/ops_reports
python3 tools/ops_visualize.py --history-dir var/ops_history --reports-dir var/ops_reports
```

**Pass:** `var/ops_reports/analytics_summary.json` exists; `schema_version` = 1.

### 3. Regenerate HTML reports

```bash
python3 tools/validate_ops_schema.py
python3 tools/generate_ops_html_report.py --reports-dir var/ops_reports
python3 tools/generate_ops_index.py --reports-dir var/ops_reports
```

**Pass:** `operations_report.html` and `index.html` open offline in browser.

### 4. Regenerate release kit

```bash
python3 tools/build_ops_release_kit.py --history-dir var/ops_history --reports-dir var/ops_reports
```

**Pass:** New directory under `var/ops_release_kit/<stamp>/` with `VERSION`, `README.txt`, `manifest.json`.

### 5. Verify checksums

```bash
cd var/ops_release_kit/<stamp>
sha256sum -c checksums.sha256
```

Or Python:

```bash
python3 -c "
from pathlib import Path
from utils.ops_release_kit import verify_release_kit_checksums
ok, err = verify_release_kit_checksums(Path('var/ops_release_kit/<stamp>'))
assert ok, err
"
```

**Pass:** Exit 0; no `checksum_mismatch` errors.

### 6. Verify schema integrity

```bash
python3 tools/validate_ops_schema.py --history-dir var/ops_history --reports-dir var/ops_reports
```

**Pass:** `status` is `OK` or `WARNING` (not `FAIL`).

## Deterministic recovery path

For reproducible verification in CI:

```bash
export OPS_FROZEN_UTC=2026-05-16T12:00:00Z
make ops-release-validate
```

## Sign-off

| Step | Operator | Date | Pass |
|------|----------|------|------|
| 1 Archive | | | ☐ |
| 2 Analytics | | | ☐ |
| 3 HTML | | | ☐ |
| 4 Release kit | | | ☐ |
| 5 Checksums | | | ☐ |
| 6 Schema | | | ☐ |

**Drill result:** ☐ PASS ☐ FAIL

## Rollback

Delete regenerated `var/ops_reports/`, `var/ops_bundle/`, `var/ops_release_kit/` — no application restart required.
