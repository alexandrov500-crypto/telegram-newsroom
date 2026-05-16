"""Reproducible operational export bundle (v3.2 P3). Read-only."""

from __future__ import annotations

import json
import shutil
from pathlib import Path
from typing import Any

from utils.ops_analytics import (
    analytics_summary_markdown,
    build_analytics_summary,
    build_shift_handoff,
    build_visualization_bundle,
    default_archive_dir,
    default_reports_dir,
)
from utils.ops_schema_governance import (
    MAX_BUNDLE_BYTES,
    build_schema_validation_report,
    sha256_file,
    validation_report_markdown,
    write_json_deterministic,
)
from utils.ops_tooling import default_history_dir, frozen_utc_now, list_snapshots


def default_bundle_root(repo_root: Path | None = None) -> Path:
    root = repo_root or Path(__file__).resolve().parents[1]
    return root / "var" / "ops_bundle"


def bundle_dir_for_stamp(root: Path, stamp: str | None = None) -> Path:
    tag = (stamp or frozen_utc_now()).replace(":", "")
    return root / tag


def export_ops_bundle(
    *,
    history_dir: Path,
    reports_dir: Path,
    archive_dir: Path,
    bundle_root: Path,
    limit: int = 200,
) -> dict[str, Any]:
    stamp = frozen_utc_now().replace(":", "")
    out = bundle_dir_for_stamp(bundle_root, stamp)
    if out.exists():
        shutil.rmtree(out)
    out.mkdir(parents=True)

    summary = build_analytics_summary(history_dir, limit=limit)
    export_summary = {k: v for k, v in summary.items() if k != "series"}
    export_summary["series_count"] = summary.get("snapshot_count")

    write_json_deterministic(out / "analytics_summary.json", export_summary)
    (out / "analytics_summary.md").write_text(analytics_summary_markdown(summary), encoding="utf-8")
    (out / "shift_handoff.md").write_text(build_shift_handoff(history_dir, hours=24.0), encoding="utf-8")

    charts = build_visualization_bundle(summary)
    for name, svg in sorted(charts.items()):
        (out / name).write_text(svg, encoding="utf-8")

    snap_dir = out / "snapshots"
    snap_dir.mkdir()
    for path in list_snapshots(history_dir)[-min(limit, 48) :]:
        shutil.copy2(path, snap_dir / path.name)

    archive_manifest: list[dict[str, str]] = []
    if archive_dir.is_dir():
        arch_out = out / "archive"
        arch_out.mkdir()
        for path in sorted(archive_dir.rglob("*.json.gz")):
            rel = path.relative_to(archive_dir)
            dest = arch_out / rel
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(path, dest)
            archive_manifest.append({"path": str(rel).replace("\\", "/")})

    validation = build_schema_validation_report(
        history_dir=history_dir,
        reports_dir=reports_dir,
        archive_dir=archive_dir,
    )
    write_json_deterministic(out / "validation_report.json", validation)
    (out / "validation_report.md").write_text(validation_report_markdown(validation), encoding="utf-8")

    manifest_files: list[dict[str, str]] = []
    total = 0
    for path in sorted(out.rglob("*")):
        if path.is_file() and path.name != "manifest.json" and path.name != "checksums.sha256":
            rel = str(path.relative_to(out)).replace("\\", "/")
            digest = sha256_file(path)
            size = path.stat().st_size
            total += size
            manifest_files.append({"path": rel, "sha256": digest, "bytes": str(size)})

    if total > MAX_BUNDLE_BYTES:
        raise ValueError(f"bundle exceeds max size: {total} > {MAX_BUNDLE_BYTES}")

    manifest: dict[str, Any] = {
        "schema_version": 1,
        "read_only": True,
        "generated_at": frozen_utc_now(),
        "bundle_stamp": stamp,
        "total_bytes": total,
        "files": manifest_files,
        "archive_entries": archive_manifest,
    }
    write_json_deterministic(out / "manifest.json", manifest)

    lines = [f"{e['sha256']}  {e['path']}" for e in manifest_files]
    (out / "checksums.sha256").write_text("\n".join(lines) + "\n", encoding="utf-8")

    return {"bundle_dir": str(out), "manifest": manifest, "validation_status": validation.get("status")}


def build_ops_html_report(
    *,
    bundle_dir: Path | None,
    validation_report: dict[str, Any] | None,
    analytics_path: Path | None,
) -> str:
    summary: dict[str, Any] = {}
    if analytics_path and analytics_path.is_file():
        summary = json.loads(analytics_path.read_text(encoding="utf-8"))

    svgs: dict[str, str] = {}
    if bundle_dir and bundle_dir.is_dir():
        for p in sorted(bundle_dir.glob("*.svg")):
            svgs[p.name] = p.read_text(encoding="utf-8")

    val_status = (validation_report or {}).get("status", "UNKNOWN")
    gen = frozen_utc_now()

    parts = [
        "<!DOCTYPE html>",
        "<html lang='en'><head><meta charset='utf-8'/>",
        "<title>Operations Report</title>",
        "<style>",
        "body{font-family:system-ui,sans-serif;margin:1.5rem;max-width:960px}",
        "h1,h2{margin-top:1.5rem} table{border-collapse:collapse;width:100%}",
        "td,th{border:1px solid #ccc;padding:.4rem .6rem;text-align:left}",
        ".ok{color:#166534}.warn{color:#a16207}.fail{color:#b91c1c}",
        "</style></head><body>",
        f"<h1>Operations report</h1><p>Generated {gen}</p>",
        f"<p>Schema validation: <strong class='{val_status.lower()}'>{val_status}</strong></p>",
        "<h2>Analytics summary</h2>",
        "<table><tr><th>Metric</th><th>Delta</th><th>Max level</th></tr>",
    ]
    for key, body in sorted((summary.get("trends") or {}).items()):
        parts.append(
            f"<tr><td>{key}</td><td>{body.get('delta_total')}</td><td>{body.get('max_level')}</td></tr>"
        )
    parts.append("</table><h2>Anomalies</h2><ul>")
    for a in (summary.get("anomaly_windows") or [])[:12]:
        parts.append(f"<li>{a.get('metric')} +{a.get('delta')} @ {a.get('captured_at')}</li>")
    if not summary.get("anomaly_windows"):
        parts.append("<li><em>None</em></li>")
    parts.append("</ul><h2>Charts</h2>")
    for name, svg in svgs.items():
        parts.append(f"<h3>{name}</h3>{svg}")
    parts.append("<h2>Shift handoff</h2><pre>")
    handoff_path = (bundle_dir / "shift_handoff.md") if bundle_dir else None
    if handoff_path and handoff_path.is_file():
        parts.append(_escape_html(handoff_path.read_text(encoding="utf-8")[:8000]))
    else:
        parts.append("No shift handoff bundle present.")
    parts.append("</pre><h2>Schema validation</h2><ul>")
    counts = (validation_report or {}).get("counts") or {}
    parts.append(f"<li>Snapshots checked: {counts.get('snapshots', 0)}</li>")
    parts.append(f"<li>Corrupt: {counts.get('corrupt', 0)}</li>")
    parts.append(f"<li>Fail: {counts.get('fail', 0)}</li>")
    parts.append("</ul><h2>Retention</h2><ul>")
    parts.append("<li>Active snapshots: var/ops_history (rotate 200 / 20MB)</li>")
    parts.append("<li>Archive: var/ops_archive (gzip)</li>")
    parts.append("<li>Reports regenerable from snapshots</li></ul>")
    parts.append("</body></html>")
    return "\n".join(parts)


def _escape_html(text: str) -> str:
    return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
