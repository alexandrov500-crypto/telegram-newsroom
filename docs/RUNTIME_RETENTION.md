# Runtime retention

## Purpose

This layer limits growth of **local filesystem outputs** used by runtime diagnostics:

- **Artifact directories** — `*.zip` bundles, regression / qualification JSON next to them.
- **Baseline directories** — rotated `*.zip` baselines.
- **Report directories** — standalone soak, benchmark, or integrity JSON (and optional HTML).

It is **not** a storage platform, object-lifecycle manager, background cleaner, or scheduler. It is a **deterministic, bounded** utility you invoke from cron, CI, or an ops runbook after producing artifacts.

The module `utils/runtime_retention.py` also hosts **`cleanup_old_runtime_snapshots`** / **`list_snapshot_files`**, used automatically when saving runtime JSON snapshots under `runtime_state_dir` (separate from the CLI artifact dirs).

## Operational semantics

### Scoping

- Only **top-level** entries under each configured directory are considered (no recursion).
- **Subdirectories are never entered or deleted**; they appear as `directory:…` in `skipped_files`.
- **Symbolic links are never deleted** (and are not selected as retention candidates); they appear as `symlink:…` in `skipped_files`.
- Missing or invalid paths produce **warnings** and are skipped (no crash).

### Filename rules (basename only)

| Root | Matched files |
|------|----------------|
| `--artifacts-dir` | `*.zip`; `*.json` whose name contains `regression` or `qualification` (case-insensitive) |
| `--baselines-dir` | `*.zip` |
| `--reports-dir` | `*.json` with `soak`, `benchmark`, or `integrity` in the name; with `--include-html`, same for `*.html` |

Other files are ignored (noise, logs, etc.).

### Policy (per root)

`--retain-count` and `--max-age-days` apply **independently within each** of artifacts / baselines / reports (not one combined pool).

1. **Age** — If `--max-age-days` > 0, any file with `mtime` older than `now − max_age_days` is deleted. If `0`, no age-based deletion.
2. **Count** — Among remaining files, keep the newest `--retain-count` by `mtime` (descending), tie-break by full path (ascending). Delete the rest in that root.

Deletion order is deterministic; `dry-run` lists the same paths without calling `unlink`.

### `--strict`

CLI exit code `1` if the report’s `warnings` list is non-empty (e.g. missing dirs, `stat`/`unlink` failures).

### Snapshot retention (in-process)

`cleanup_old_runtime_snapshots(settings)` enforces `runtime_snapshots_max_count`, `runtime_snapshots_max_age_hours`, and `runtime_snapshots_max_storage_bytes` on `snapshot_*.json` under `runtime_state_dir`. When `runtime_snapshots_max_age_hours <= 0` (unit tests), age pruning uses a **1 second** floor so brand-new snapshots are not wiped.

## CLI

```bash
python tools/runtime_retention.py \
  --artifacts-dir artifacts \
  --baselines-dir runtime_baselines
```

Common flags:

| Flag | Meaning |
|------|---------|
| `--reports-dir` | Optional third root for standalone reports |
| `--retain-count` | Per-root cap after age filter (default `20`) |
| `--max-age-days` | Per-root max age; `0` disables (default) |
| `--dry-run` | Plan only |
| `--include-html` | Allow HTML under `--reports-dir` |
| `--json-output` / `--output-report` | Persist machine / human summaries |
| `--strict` | Fail on warnings |

## JSON report (`--json-output`)

Stable keys (use `json.dumps(..., sort_keys=True)` from the tool):

- `scanned_files`, `retained_files`, `deleted_files`, `skipped_files` (sorted path strings)
- `total_bytes_before`, `total_bytes_after`, `reclaimed_bytes`
- `warnings`, `dry_run`

## Example human summary

```
Runtime retention summary

Files scanned (eligible): 42
Files retained: 18
Files deleted: 24
Files skipped (symlinks/dirs): 3
Space reclaimed: 192937984 bytes (184.0 MB)

Dry-run: false
```

## Recommended policies

| Environment | retain-count | max-age-days | Notes |
|-------------|--------------|---------------|--------|
| Dev laptop | 5–10 | 7–14 | Small disk |
| CI workspace | 10–30 | 3–7 | Match artifact upload window |
| Release host | 20–50 | 14–30 | Keep a few baselines per train |

Tune independently per directory by running the tool twice with different roots if needed (future improvement: per-root flags).

## Example nightly flow (documentation only)

1. Benchmark  
2. Soak  
3. Artifact bundle (`build_runtime_artifact_bundle`)  
4. Regression compare (`compare_runtime_baseline`)  
5. Release qualification (`release_qualification`)  
6. **Retention** — `tools/runtime_retention.py` with `--dry-run` first in prod rollouts  
7. Upload retained artifacts  

## Implementation map

| Piece | Location |
|-------|----------|
| Scan / classify / apply / report | `utils/runtime_retention.py` |
| CLI | `tools/runtime_retention.py` |
| Tests | `tests/runtime/test_runtime_retention.py` |
| Snapshot hooks | `utils/runtime_state_store.py` |
