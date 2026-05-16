# Runtime artifact bundle

This repository ships a **single zip bundle** (`runtime_bundle/`) that groups JSON snapshots useful for **CI nightly retention**, **operator handoff**, and **postmortem** analysis—without turning the app into a telemetry platform.

## Contents

When you run `tools/build_runtime_artifact_bundle.py`, the zip contains (under `runtime_bundle/`):

| Member | Source |
|--------|--------|
| `benchmark.json` | `tools/runtime_benchmark.build_benchmark_payload` (same as benchmark CLI sync slice) |
| `stability.json` | `async_main(..., sample_transport=False)` from the same module (full snapshot JSON) |
| `integrity.json` | `utils.runtime_integrity` validators + `summarize_runtime_state_dir` |
| `runtime_summary.json` | `summarize_runtime_state_dir` + `utils.soak_simulation.collect_bounded_state_report` |
| `environment.json` | `pid`, `cwd`, `redis_enabled` from `Settings`, optional `soak_profile` / `sample_transport_enabled` from `--metadata-json` |
| `manifest.json` | Bundle metadata (sizes, missing optional files, git sha best-effort, etc.) |
| `soak_report.json` | Optional: must exist under `RUNTIME_STATE_DIR` if you want it included (e.g. written by `tools/soak_runner.py --json-out …` copied to `soak_report.json`) |
| `soak_report.html` | Optional: only when `--include-html` and file present |
| `queue_pressure.json` | Optional: drop a JSON export from `admin_cli queue-pressure` or your own collector beside state files |

Missing optional files are listed in `manifest.missing_files`. With `--fail-on-missing`, the tool exits non-zero if any optional file is absent (use after soak + queue export in strict CI).

## Local usage

The bundle CLI uses `load_settings()` from `app.config` (same required environment variables as the main app: `OPENAI_API_KEY`, `BOT_TOKEN`, Telegram identifiers, etc.). Point `--runtime-dir` at the directory that holds `operational_timeline.json` and friends (typically `RUNTIME_STATE_DIR`); the tool overrides `runtime_state_dir` on the loaded `Settings` to match that path.

```bash
# 1) Produce soak JSON beside runtime state (example paths)
python tools/soak_runner.py --profile low --max-ticks 50 --json-out runtime_state/soak_report.json

# 2) Optional: export queue pressure (requires Redis stack — skip in offline dev)
# python tools/admin_cli.py queue-pressure --kind ingest --json > runtime_state/queue_pressure.json

# 3) Bundle
python tools/build_runtime_artifact_bundle.py \
  --runtime-dir runtime_state \
  --output artifacts/runtime_bundle.zip
```

Optional metadata (soak profile label, CI job id, etc.):

```bash
echo '{"soak_profile":"low","sample_transport_enabled":false,"manifest_extra":{"ci_job":"local"}}' > /tmp/meta.json
python tools/build_runtime_artifact_bundle.py \
  --runtime-dir runtime_state \
  --output artifacts/runtime_bundle.zip \
  --metadata-json /tmp/meta.json
```

## Nightly CI

Typical flow:

1. Run `tools/runtime_benchmark.py` (optionally `--sample-transport` on hosts with Redis).
2. Run a **short** soak (`tools/soak_runner.py --max-ticks …`) and write `soak_report.json` into the runtime dir (or copy output to that name).
3. Run `tools/build_runtime_artifact_bundle.py` targeting the same `RUNTIME_STATE_DIR`.
4. Upload `artifacts/runtime_bundle.zip` via `actions/upload-artifact`.

## Postmortem workflow

1. Download the bundle zip from CI or copy from the host.
2. Unzip; read `manifest.json` for missing pieces and byte sizes.
3. Open `integrity.json` and `runtime_summary.json` first (fast signal on timeline/suppression/bounded state).
4. Use `stability.json` / `benchmark.json` for in-process counters and RSS snapshot context.
5. If present, correlate `soak_report.json` with the incident window.

## Example: GitHub Actions (nightly)

```yaml
name: nightly-runtime-bundle
on:
  schedule: [{ cron: "0 3 * * *" }]
jobs:
  bundle:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: "3.12"
      - run: pip install -r requirements.txt
      - run: |
          mkdir -p runtime_state artifacts
          export RUNTIME_STATE_DIR=$PWD/runtime_state
          python tools/soak_runner.py --profile low --max-ticks 80 --json-out runtime_state/soak_report.json
          echo '{"soak_profile":"low","manifest_extra":{"workflow":"nightly"}}' > /tmp/bundle_meta.json
          python tools/build_runtime_artifact_bundle.py \
            --runtime-dir runtime_state \
            --output artifacts/runtime_bundle.zip \
            --metadata-json /tmp/bundle_meta.json
      - uses: actions/upload-artifact@v4
        with:
          name: runtime-bundle
          path: artifacts/runtime_bundle.zip
```

## Implementation notes

- Zip write is **atomic** (`*.tmp` then `os.replace`).
- Staging uses a **TemporaryDirectory**; no stale dirs left behind.
- **No Redis** is required for the bundle itself; optional `queue_pressure.json` is your choice to add upstream.
- Compare bundles with `tools/compare_runtime_baseline.py` — see `docs/RUNTIME_REGRESSION.md`.
