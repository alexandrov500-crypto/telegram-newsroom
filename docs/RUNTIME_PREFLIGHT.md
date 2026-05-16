# Runtime preflight

## Purpose

**Runtime preflight** is a **one-shot, bounded** startup readiness check. It validates filesystem paths, attempts to load `Settings`, probes SQLite when the app uses SQLite, scans critical runtime JSON with existing integrity helpers, optionally checks disk headroom, and optionally pings Redis—without running a daemon, scheduler, or deployment orchestrator.

Use it **before** starting workers or long soak jobs to catch misconfiguration early.

## What it is not

- Not a healthcheck service or live monitor  
- Not a deployment / rollout manager  
- Not a metrics UI  

## Checks (fixed order in the human report)

| Block | Behavior |
|-------|-----------|
| **Filesystem** | For each provided `--runtime-dir`, `--artifacts-dir`, `--reports-dir`: path exists, is a directory, is writable, and a small temp file can be created and removed. If **none** of the three are passed, status is **WARNING** (`no_directories_specified`). |
| **Settings** | `load_settings()` in the CLI (or injected `Settings` in tests). Failure → **FAIL**; empty critical string fields → **WARNING**. |
| **SQLite** | If backend is SQLite: sync `SELECT 1` with a short connect timeout. Non-SQLite URL → **WARNING** (`preflight_skipped_non_sqlite_backend`). No settings → **SKIPPED**. |
| **Runtime state** | Uses `validate_operational_timeline`, `validate_suppression_state`, `validate_event_history` on the resolved runtime dir. Invalid JSON on disk → **FAIL**; structural issues (e.g. unexpected timeline version) → **WARNING**. |
| **Disk space** | Only with `--check-disk-space`: `shutil.disk_usage` at the runtime anchor vs `--min-free-mb`. |
| **Redis** | Only with `--check-redis`: single synchronous `PING` with connect/socket timeout **1s**, no retry loop. Disabled in settings or flag off → **SKIPPED**. |
| **Artifacts layout** | If `--artifacts-dir` / `--reports-dir` are set but the path is not a directory → **WARNING** (retention-safe layout hint). |

## Outcomes

- **`preflight_ok`**: `false` only when **overall_status** is `FAIL` (warnings alone still yield `preflight_ok: true`).  
- **`overall_status`**: `FAIL` if any block is `FAIL`; else `WARNING` if any block is `WARNING`; else `OK`. `SKIPPED` does not raise the overall status.

### `--strict` exit semantics

- **Without `--strict`**: process exit code `1` only when `preflight_ok` is false (i.e. any **FAIL**).  
- **With `--strict`**: exit `1` when `overall_status != OK` (so **WARNING** fails the process too).

## CLI

```bash
python tools/runtime_preflight.py \
  --runtime-dir ./runtime_state \
  --artifacts-dir ./artifacts \
  --reports-dir ./reports \
  --check-disk-space \
  --min-free-mb 500 \
  --json-output preflight.json \
  --output-report preflight.txt
```

Optional Redis:

```bash
python tools/runtime_preflight.py --runtime-dir ./runtime_state --check-redis --strict
```

## JSON report

Written with `sort_keys=True` from the tool. Top-level keys include `checks` (per-block `status`, `detail`, `messages`), `flat_messages`, `generated_at`, `overall_status`, `preflight_ok`. The `checks` object uses **alphabetical** key order in JSON (stable with `sort_keys=True`), while the **text report** lists blocks in operational order (`filesystem` → … → `artifacts`).

## Example text summary

```
Runtime preflight summary

[OK] Filesystem
[OK] Settings
[OK] SQLite
[WARNING] Runtime state
[SKIPPED] Disk space
[SKIPPED] Redis
[OK] Artifacts layout

Overall: WARNING
PREFLIGHT_OK: true
```

## Recommended startup flow (documentation only)

1. **Runtime preflight** — `tools/runtime_preflight.py` (optionally `--strict` in CI).  
2. Benchmark / diagnostics (optional).  
3. Runtime startup (worker / bot).  
4. Soak / reliability workflows.  
5. Qualification + operational dashboard generation.  

## Implementation

| Piece | Path |
|-------|------|
| Checks + report | `utils/runtime_preflight.py` |
| CLI | `tools/runtime_preflight.py` |
| Tests | `tests/runtime/test_runtime_preflight.py` |
