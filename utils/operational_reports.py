"""Static HTML snapshots for operational bundles (no template engine)."""

from __future__ import annotations

import html
import json
from typing import Any


def _esc(x: Any) -> str:
    return html.escape(str(x), quote=True)


def render_operational_html_bundle(bundle: dict[str, Any], *, title: str = "Newsroom operational snapshot") -> str:
    """Single-file HTML from ``OperationalDashboardBundle.to_dict()`` or equivalent."""
    parts: list[str] = []
    parts.append("<!DOCTYPE html><html><head><meta charset=\"utf-8\">")
    parts.append(f"<title>{_esc(title)}</title>")
    parts.append("<style>body{font-family:system-ui,Segoe UI,sans-serif;margin:1rem 1.25rem;max-width:1100px}")
    parts.append("table{border-collapse:collapse;margin:0.5rem 0}td,th{border:1px solid #ccc;padding:4px 8px;font-size:13px}")
    parts.append("pre{background:#f6f8fa;padding:8px;overflow:auto;font-size:12px}</style></head><body>")
    parts.append(f"<h1>{_esc(title)}</h1>")
    parts.append(f"<p>schema_version={_esc(bundle.get('schema_version'))} generated_at_unix={_esc(bundle.get('generated_at_unix'))}</p>")

    ed = bundle.get("editorial_operational") or {}
    if isinstance(ed, dict) and ed:
        parts.append("<h2>Editorial operational analytics</h2><table>")
        for k, v in sorted(ed.items()):
            parts.append(f"<tr><th>{_esc(k)}</th><td>{_esc(v)}</td></tr>")
        parts.append("</table>")

    warns = bundle.get("warnings") or []
    if warns:
        parts.append("<h2>Runtime warnings</h2><ul>")
        for w in warns:
            if not isinstance(w, dict):
                continue
            parts.append(
                "<li><b>"
                + _esc(w.get("code"))
                + "</b> ("
                + _esc(w.get("severity"))
                + ") — "
                + _esc(w.get("message"))
                + "</li>"
            )
        parts.append("</ul>")

    tl = bundle.get("timeline_tail") or []
    if tl:
        parts.append("<h2>Timeline (newest first)</h2><table><tr><th>ts</th><th>kind</th><th>payload</th></tr>")
        for row in tl[:48]:
            if not isinstance(row, dict):
                continue
            pl = row.get("payload")
            pj = json.dumps(pl, ensure_ascii=False, default=str) if pl is not None else ""
            parts.append(
                "<tr><td>"
                + _esc(row.get("ts"))
                + "</td><td>"
                + _esc(row.get("kind"))
                + "</td><td><pre>"
                + _esc(pj[:2000])
                + ("…" if len(pj) > 2000 else "")
                + "</pre></td></tr>"
            )
        parts.append("</table>")

    parts.append("<h2>Raw bundle JSON</h2><pre>" + _esc(json.dumps(bundle, indent=2, ensure_ascii=False, default=str)[:120_000]) + "</pre>")
    parts.append("</body></html>")
    return "".join(parts)
