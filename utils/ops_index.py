"""Static operations index HTML (v3.2 P4). Read-only."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from utils.ops_release_kit import OPS_TOOLING_RELEASE_VERSION, governance_versions_block
from utils.ops_tooling import frozen_utc_now


def _escape(text: str) -> str:
    return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def _load_validation_summary(reports_dir: Path) -> dict[str, Any]:
    path = reports_dir / "validation_report.json"
    if not path.is_file():
        return {"status": "UNKNOWN", "counts": {}}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {"status": "CORRUPT", "counts": {}}


def build_ops_index_html(
    *,
    reports_dir: Path,
    release_kit_root: Path | None = None,
    bundle_root: Path | None = None,
) -> str:
    validation = _load_validation_summary(reports_dir)
    val_status = validation.get("status", "UNKNOWN")
    counts = validation.get("counts") or {}
    versions = governance_versions_block()
    gen = frozen_utc_now()

    report_links: list[tuple[str, str]] = []
    for name in (
        "operations_report.html",
        "analytics_summary.json",
        "analytics_summary.md",
        "validation_report.json",
        "validation_report.md",
    ):
        if (reports_dir / name).is_file():
            report_links.append((name, name))

    for svg in sorted(reports_dir.glob("*.svg")):
        report_links.append((svg.name, svg.name))

    kit_rows: list[str] = []
    if release_kit_root and release_kit_root.is_dir():
        for kit in sorted(release_kit_root.iterdir(), reverse=True):
            if not kit.is_dir() or kit.name.startswith("."):
                continue
            readme = kit / "README.txt"
            manifest = kit / "manifest.json"
            rel_base = Path("..") / "ops_release_kit" / kit.name
            kit_rows.append(
                f"<tr><td>{_escape(kit.name)}</td>"
                f"<td><a href='{_escape(str(rel_base / 'README.txt'))}'>README</a></td>"
                f"<td>{'yes' if manifest.is_file() else 'no'}</td></tr>"
            )
            if len(kit_rows) >= 12:
                break

    bundle_rows: list[str] = []
    if bundle_root and bundle_root.is_dir():
        for bundle in sorted(bundle_root.iterdir(), reverse=True):
            if not bundle.is_dir() or bundle.name.startswith("."):
                continue
            rel = Path("..") / "ops_bundle" / bundle.name / "manifest.json"
            bundle_rows.append(f"<li><a href='{_escape(str(rel))}'>{_escape(bundle.name)}</a></li>")
            if len(bundle_rows) >= 8:
                break

    parts = [
        "<!DOCTYPE html>",
        "<html lang='en'><head><meta charset='utf-8'/>",
        "<title>Operations index</title>",
        "<style>",
        "body{font-family:system-ui,sans-serif;margin:1.5rem;max-width:900px}",
        "table{border-collapse:collapse;width:100%} td,th{border:1px solid #ccc;padding:.4rem}",
        "a{color:#1d4ed8}",
        "</style></head><body>",
        f"<h1>Operations index</h1>",
        f"<p>Generated {_escape(gen)} · Tooling {_escape(OPS_TOOLING_RELEASE_VERSION)}</p>",
        "<h2>Schema versions</h2><ul>",
    ]
    for k, v in sorted(versions.items()):
        parts.append(f"<li>{_escape(k)}: {v}</li>")
    parts.append("</ul>")
    parts.append(f"<h2>Validation summary</h2><p>Status: <strong>{_escape(str(val_status))}</strong></p>")
    parts.append("<ul>")
    parts.append(f"<li>Snapshots checked: {counts.get('snapshots', '—')}</li>")
    parts.append(f"<li>Corrupt: {counts.get('corrupt', 0)}</li>")
    parts.append(f"<li>Fail: {counts.get('fail', 0)}</li>")
    parts.append("</ul>")
    parts.append("<h2>Reports (this directory)</h2><ul>")
    for label, href in report_links:
        parts.append(f"<li><a href='{_escape(href)}'>{_escape(label)}</a></li>")
    if not report_links:
        parts.append("<li><em>No reports yet — run ops_analytics_aggregate / generate_ops_html_report</em></li>")
    parts.append("</ul>")
    parts.append("<h2>Retention</h2><ul>")
    parts.append("<li>var/ops_history — max 200 files / 20MB</li>")
    parts.append("<li>var/ops_archive — gzip snapshots</li>")
    parts.append("<li>Regenerate reports from snapshots anytime (offline)</li>")
    parts.append("</ul>")
    parts.append("<h2>Release kits</h2>")
    if kit_rows:
        parts.append("<table><tr><th>Stamp</th><th>Kit</th><th>Manifest</th></tr>")
        parts.extend(kit_rows)
        parts.append("</table>")
    else:
        parts.append("<p><em>No release kits found under var/ops_release_kit/</em></p>")
    parts.append("<h2>Recent bundles</h2><ul>")
    parts.extend(bundle_rows or ["<li><em>None</em></li>"])
    parts.append("</ul></body></html>")
    return "\n".join(parts)
