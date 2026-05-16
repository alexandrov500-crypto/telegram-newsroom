# Operational dashboard

## Purpose

The operational dashboard is a **single static HTML file** that summarizes what you already collected:

- `runtime_bundle.zip` (manifest, stability, runtime summary, …)
- Optional `qualification.json` (from `tools/release_qualification.py`)
- Optional `regression.json` (from `tools/compare_runtime_baseline.py`)
- Optional `retention.json` (from `tools/runtime_retention.py`)

It is **not** a web service, live metrics UI, SPA, or observability platform. There is no JavaScript, no external CSS, and no auto-refresh—open the file in any browser **offline**.

## Sections (fixed order)

1. **Overview** — `generated_at`, qualification status, `RELEASE_READY`, baseline path, bundle path, `git_sha` from manifest when present.
2. **Runtime summary** — bounded state keys, queue hints, moderation fields, a bounded subset of reliability counters.
3. **Regression summary** — overall status, full metric table (deterministic `METRIC_ORDER`), “top regressions” (non-OK rows).
4. **Qualification** — per-check status, warnings/failures lists.
5. **Retention** — scanned/retained/deleted counts, reclaimed bytes, dry-run flag (when JSON provided).
6. **Artifacts** — manifest `included_files`, `missing_files`, sizes, bundle version.
7. **Input warnings** — missing paths, bad zip, corrupt sidecar JSON, etc.

With `--include-json-snippets`, a final **JSON snippets** section appends bounded `json.dumps` of each rendered section body (for diffing / audits).

## Status badges

Statuses render as `[OK]`, `[WARNING]`, `[FAIL]` with simple color classes (`badge-ok`, `badge-warn`, `badge-fail`). Unknown values use `[UNKNOWN]` / `badge-unknown`.

## CLI

```bash
python tools/build_operational_dashboard.py \
  --runtime-bundle artifacts/runtime_bundle.zip \
  --qualification-report qualification.json \
  --regression-report regression.json \
  --retention-report retention.json \
  --output operational_dashboard.html \
  --title "Nightly runtime"
```

| Flag | Role |
|------|------|
| `--runtime-bundle` | Current bundle zip (optional) |
| `--qualification-report` | Qualification JSON (optional) |
| `--regression-report` | Regression JSON (optional) |
| `--retention-report` | Retention JSON (optional) |
| `--output` | Destination `.html` |
| `--title` | `<title>` and `<h1>` |
| `--include-json-snippets` | Append raw JSON snippets section |
| `--strict` | Exit non-zero if any **input** warnings occurred |

Missing inputs degrade gracefully: sections show *n/a* or *No … report* and warnings are listed.

## Offline usage

1. Copy the HTML next to your artifacts (or download from CI).
2. Open locally in a browser (`file://` is fine).
3. No network access required.

## Nightly artifact usage

Attach `operational_dashboard.html` beside `runtime_bundle.zip`, regression/qualification JSON, and retention report so reviewers get one scrollable summary without unzipping first.

## Postmortem workflow

1. Fetch bundle + sidecar JSON from the incident window.
2. Regenerate the dashboard with the same paths (or re-run qualification/regression if you still have baseline/current zips).
3. Read **Overview** + **Qualification** first, then **Regression** / **Runtime summary**, then **Artifacts** / **Input warnings** for gaps.

## Example HTML snippet

```html
<section id="overview"><h2>Overview</h2>
<div class="section">
<p><span class="badge badge-ok">[OK]</span> <strong>Qualification</strong>: OK</p>
<p><strong>RELEASE_READY</strong>: true</p>
<p><strong>Baseline</strong>: /data/stable_bundle.zip</p>
...
</div></section>
```

(No screenshots in-repo; the snippet above reflects actual generator output.)

## Example nightly flow (documentation only)

1. Benchmark  
2. Soak  
3. Artifact bundle  
4. Regression comparison  
5. Release qualification  
6. Retention cleanup  
7. **Operational dashboard** — `build_operational_dashboard.py`  
8. Upload retained artifacts + HTML  

## Implementation

| Piece | Path |
|-------|------|
| Loader + HTML | `utils/operational_dashboard.py` |
| CLI | `tools/build_operational_dashboard.py` |
| Tests | `tests/runtime/test_operational_dashboard.py` |
