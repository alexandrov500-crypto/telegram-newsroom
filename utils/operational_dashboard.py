"""Static operational HTML dashboard from runtime bundle + JSON reports (read-only, deterministic)."""

from __future__ import annotations

import json
import time
from html import escape
from pathlib import Path
from typing import Any

from utils.runtime_regression import METRIC_LABELS, METRIC_ORDER, load_runtime_bundle

_METRIC_INDEX = {m: i for i, m in enumerate(METRIC_ORDER)}


def _safe_json_file(path: Path | None, *, label: str) -> tuple[dict[str, Any] | None, list[str]]:
    warns: list[str] = []
    if path is None:
        return None, warns
    p = path.expanduser().resolve()
    if not p.is_file():
        warns.append(f"missing_json:{label}:{p}")
        return None, warns
    try:
        raw = p.read_bytes()
    except OSError as exc:
        warns.append(f"read_failed:{label}:{p}:{exc!r}")
        return None, warns
    try:
        data = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError, TypeError) as exc:
        warns.append(f"invalid_json:{label}:{type(exc).__name__}")
        return None, warns
    if not isinstance(data, dict):
        warns.append(f"invalid_json:{label}:expected_object")
        return None, warns
    return data, warns


def load_dashboard_inputs(
    *,
    runtime_bundle: Path | None,
    qualification_report: Path | None,
    regression_report: Path | None,
    retention_report: Path | None,
) -> dict[str, Any]:
    """Load all inputs; never raises for I/O or JSON (warnings instead)."""
    all_warns: list[str] = []
    bundle: dict[str, Any] = {}
    if runtime_bundle is not None:
        bundle, w = load_runtime_bundle(runtime_bundle)
        all_warns.extend([f"bundle:{x}" for x in w])
    qual, wq = _safe_json_file(qualification_report, label="qualification")
    all_warns.extend(wq)
    reg, wr = _safe_json_file(regression_report, label="regression")
    all_warns.extend(wr)
    ret, wt = _safe_json_file(retention_report, label="retention")
    all_warns.extend(wt)
    return {
        "bundle": bundle,
        "bundle_path": str(runtime_bundle.resolve()) if runtime_bundle else "",
        "qualification": qual,
        "regression": reg,
        "retention": ret,
        "warnings": sorted(set(all_warns)),
    }


def render_status_badge(status: str) -> str:
    """Self-contained HTML badge (text + minimal class)."""
    st = str(status or "UNKNOWN").strip().upper()
    if st not in ("OK", "WARNING", "FAIL"):
        st = "UNKNOWN"
    cls = {"OK": "badge-ok", "WARNING": "badge-warn", "FAIL": "badge-fail"}.get(st, "badge-unknown")
    return f'<span class="badge {cls}">[{escape(st)}]</span>'


def _status_rank(st: str) -> int:
    return {"FAIL": 0, "WARNING": 1, "OK": 2}.get(st.upper(), 3)


def extract_dashboard_sections(inputs: dict[str, Any]) -> list[tuple[str, dict[str, Any]]]:
    """Build section bodies for rendering (deterministic keys / ordering)."""
    bundle = inputs.get("bundle") or {}
    qual = inputs.get("qualification")
    reg = inputs.get("regression")
    ret = inputs.get("retention")
    manifest = bundle.get("manifest.json") if isinstance(bundle.get("manifest.json"), dict) else {}
    summary = bundle.get("runtime_summary.json") if isinstance(bundle.get("runtime_summary.json"), dict) else {}
    stability = bundle.get("stability.json") if isinstance(bundle.get("stability.json"), dict) else {}
    benchmark = bundle.get("benchmark.json") if isinstance(bundle.get("benchmark.json"), dict) else {}

    overview: dict[str, Any] = {
        "baseline_bundle": "",
        "bundle_path": str(inputs.get("bundle_path") or ""),
        "git_sha": manifest.get("git_sha"),
        "qualification_status": None,
        "release_ready": None,
    }
    if isinstance(qual, dict):
        overview["qualification_status"] = qual.get("qualification_status")
        overview["release_ready"] = qual.get("release_ready")
        overview["baseline_bundle"] = qual.get("baseline_bundle") or ""
    if isinstance(reg, dict) and not overview["baseline_bundle"]:
        overview["baseline_bundle"] = str(reg.get("baseline_bundle") or "")

    bounded = (summary.get("bounded_state_report") or {}) if isinstance(summary, dict) else {}
    derived = (stability.get("derived") or {}) if isinstance(stability, dict) else {}
    editorial = (stability.get("editorial_analytics") or {}) if isinstance(stability, dict) else {}
    if not editorial and isinstance(benchmark, dict):
        editorial = benchmark.get("editorial_analytics") or {}
    counters = {}
    if isinstance(stability, dict):
        me = stability.get("metrics_export") or {}
        if isinstance(me, dict):
            counters = me.get("counters") or {}
    if not counters and isinstance(benchmark, dict):
        me = benchmark.get("metrics_export") or {}
        if isinstance(me, dict):
            counters = me.get("counters") or {}

    runtime_summary: dict[str, Any] = {
        "bounded_state": {k: bounded.get(k) for k in sorted(bounded.keys())[:80]} if isinstance(bounded, dict) else {},
        "moderation": {
            "avg_publish_attempts_recent": editorial.get("avg_publish_attempts_ring"),
            "moderation_latency_avg_sec": editorial.get("moderation_latency_avg_sec"),
        },
        "queue": {
            "avg_oldest_pending_age_sec_sampled_kinds": derived.get("avg_oldest_pending_age_sec_sampled_kinds"),
            "queue_depth_by_kind": stability.get("queue_depth_by_kind") if isinstance(stability, dict) else None,
        },
        "reliability_counters": {k: counters[k] for k in sorted(counters.keys())[:48]} if isinstance(counters, dict) else {},
    }

    reg_rows: list[dict[str, Any]] = []
    reg_overall = "UNKNOWN"
    reg_warn_rows: list[dict[str, Any]] = []
    if isinstance(reg, dict):
        reg_overall = str(reg.get("overall_status") or "UNKNOWN")
        rows = reg.get("metrics") or []
        if isinstance(rows, list):
            for row in rows:
                if isinstance(row, dict):
                    reg_rows.append(row)
            non_ok = [r for r in reg_rows if str(r.get("status") or "OK").upper() != "OK"]
            reg_warn_rows = sorted(
                non_ok,
                key=lambda r: (_status_rank(str(r.get("status"))), str(r.get("metric") or "")),
            )[:16]

    qualification_block: dict[str, Any] = {}
    if isinstance(qual, dict):
        qualification_block = {
            "checks": qual.get("checks") or {},
            "failures": qual.get("failures") or [],
            "qualification_status": qual.get("qualification_status"),
            "release_ready": qual.get("release_ready"),
            "warnings": qual.get("warnings") or [],
        }

    retention_block: dict[str, Any] = {}
    if isinstance(ret, dict):
        retention_block = {
            "deleted_files": len(ret.get("deleted_files") or []),
            "dry_run": ret.get("dry_run"),
            "reclaimed_bytes": ret.get("reclaimed_bytes"),
            "retained_files": len(ret.get("retained_files") or []),
            "scanned_files": len(ret.get("scanned_files") or []),
        }

    artifacts_block: dict[str, Any] = {
        "artifact_sizes": manifest.get("artifact_sizes") if isinstance(manifest.get("artifact_sizes"), dict) else {},
        "bundle_version": manifest.get("bundle_version"),
        "generated_at": manifest.get("generated_at"),
        "included_files": manifest.get("included_files") or [],
        "missing_files": manifest.get("missing_files") or [],
    }
    if isinstance(artifacts_block["included_files"], list):
        artifacts_block["included_files"] = sorted(str(x) for x in artifacts_block["included_files"])
    if isinstance(artifacts_block["missing_files"], list):
        artifacts_block["missing_files"] = sorted(str(x) for x in artifacts_block["missing_files"])

    warn_section = {"items": list(inputs.get("warnings") or [])}

    return [
        ("overview", overview),
        ("runtime_summary", runtime_summary),
        (
            "regression_summary",
            {"overall": reg_overall, "rows": reg_rows, "top_regressions": reg_warn_rows},
        ),
        ("qualification", qualification_block),
        ("retention", retention_block),
        ("artifacts", artifacts_block),
        ("input_warnings", warn_section),
    ]


def build_dashboard_payload(
    *,
    runtime_bundle: Path | None,
    qualification_report: Path | None,
    regression_report: Path | None,
    retention_report: Path | None,
    title: str,
) -> dict[str, Any]:
    inputs = load_dashboard_inputs(
        runtime_bundle=runtime_bundle,
        qualification_report=qualification_report,
        regression_report=regression_report,
        retention_report=retention_report,
    )
    sections = extract_dashboard_sections(inputs)
    return {
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "input_warnings": list(inputs.get("warnings") or []),
        "sections": sections,
        "title": title,
    }


def _css() -> str:
    return """
body{font-family:system-ui,-apple-system,sans-serif;margin:1.25rem;color:#111827;line-height:1.45;max-width:1100px}
h1{font-size:1.25rem;margin:0 0 0.5rem}
h2{font-size:1.05rem;margin:1.5rem 0 0.5rem;border-bottom:1px solid #e5e7eb;padding-bottom:0.25rem}
.meta{color:#6b7280;font-size:0.9rem;margin-bottom:1rem}
table{border-collapse:collapse;width:100%;font-size:0.9rem;margin:0.5rem 0}
th,td{border:1px solid #e5e7eb;padding:0.35rem 0.5rem;text-align:left;vertical-align:top}
th{background:#f9fafb}
pre{background:#f3f4f6;padding:0.75rem;border-radius:6px;overflow:auto;font-size:0.82rem}
.badge{font-weight:600;margin-right:0.35rem}
.badge-ok{color:#15803d}
.badge-warn{color:#b45309}
.badge-fail{color:#b91c1c}
.badge-unknown{color:#6b7280}
ul{margin:0.25rem 0 0.5rem 1.1rem}
.section{margin-bottom:0.25rem}
"""


def render_dashboard_html(
    payload: dict[str, Any],
    *,
    include_json_snippets: bool,
) -> str:
    """Single self-contained HTML document (no external assets, no JS)."""
    title = str(payload.get("title") or "Operational dashboard")
    gen = escape(str(payload.get("generated_at") or ""))
    sections_html: list[str] = []
    raw_parts: list[str] = []

    for sid, body in payload.get("sections") or []:
        if sid == "overview":
            inner = _render_overview_section(body)
        elif sid == "runtime_summary":
            inner = _render_runtime_section(body)
        elif sid == "regression_summary":
            inner = _render_regression_section(body)
        elif sid == "qualification":
            inner = _render_qualification_section(body)
        elif sid == "retention":
            inner = _render_retention_section(body)
        elif sid == "artifacts":
            inner = _render_artifacts_section(body)
        elif sid == "input_warnings":
            inner = _render_warnings_section(body)
        else:
            inner = f"<pre>{escape(json.dumps(body, sort_keys=True, default=str)[:8000])}</pre>"
        sections_html.append(f'<section id="{escape(sid)}"><h2>{escape(_section_title(sid))}</h2>{inner}</section>')
        if include_json_snippets:
            raw_parts.append(f"<h3>{escape(sid)}</h3><pre>{escape(json.dumps(body, sort_keys=True, default=str)[:12000])}</pre>")

    extra = ""
    if include_json_snippets and raw_parts:
        extra = '<section id="raw-json"><h2>JSON snippets</h2>' + "\n".join(raw_parts) + "</section>"

    css = _css()
    body = f"""<header><h1>{escape(title)}</h1><div class="meta">generated_at: {gen}</div></header>
{"".join(sections_html)}
{extra}"""
    return f"""<!DOCTYPE html>
<html lang="en"><head><meta charset="utf-8"/><title>{escape(title)}</title>
<style>{css}</style></head><body>
{body}
</body></html>"""


def _section_title(sid: str) -> str:
    return {
        "overview": "Overview",
        "runtime_summary": "Runtime summary",
        "regression_summary": "Regression summary",
        "qualification": "Qualification",
        "retention": "Retention",
        "artifacts": "Artifacts",
        "input_warnings": "Input warnings",
    }.get(sid, sid)


def _render_overview_section(data: dict[str, Any]) -> str:
    qs = data.get("qualification_status")
    rr = data.get("release_ready")
    ready_txt = "unknown" if rr is None else str(bool(rr)).lower()
    qual_badge = render_status_badge(str(qs) if qs else "UNKNOWN")
    lines = [
        '<div class="section">',
        f"<p>{qual_badge} <strong>Qualification</strong>: {escape(str(qs) if qs is not None else 'n/a')}</p>",
        f"<p><strong>RELEASE_READY</strong>: {escape(ready_txt)}</p>",
        f"<p><strong>Baseline</strong>: {escape(str(data.get('baseline_bundle') or 'n/a'))}</p>",
        f"<p><strong>Runtime bundle</strong>: {escape(str(data.get('bundle_path') or 'n/a'))}</p>",
        f"<p><strong>git sha</strong> (manifest): {escape(str(data.get('git_sha') or 'n/a'))}</p>",
        "</div>",
    ]
    return "\n".join(lines)


def _render_runtime_section(data: dict[str, Any]) -> str:
    parts = ["<h3>Bounded state</h3>", _kv_table(data.get("bounded_state") or {})]
    parts.append("<h3>Queue</h3>")
    q = data.get("queue") or {}
    parts.append(_kv_table({k: q[k] for k in sorted(q.keys()) if q[k] is not None}))
    parts.append("<h3>Moderation</h3>")
    parts.append(_kv_table(data.get("moderation") or {}))
    parts.append("<h3>Reliability counters (subset)</h3>")
    parts.append(_kv_table(data.get("reliability_counters") or {}))
    return "\n".join(parts)


def _kv_table(obj: dict[str, Any]) -> str:
    if not obj:
        return "<p><em>No data</em></p>"
    rows = "".join(
        f"<tr><th>{escape(str(k))}</th><td><pre>{escape(json.dumps(v, sort_keys=True, default=str)[:2000])}</pre></td></tr>"
        for k, v in sorted(obj.items(), key=lambda kv: str(kv[0]))
    )
    return f"<table><tbody>{rows}</tbody></table>"


def _render_regression_section(data: dict[str, Any]) -> str:
    overall = str(data.get("overall") or "UNKNOWN")
    badge = render_status_badge(overall)
    rows = data.get("rows") or []
    top = data.get("top_regressions") or []
    head = f"<p>{badge} <strong>Overall</strong>: {escape(overall)}</p>"
    if not isinstance(rows, list) or not rows:
        return head + "<p><em>No regression report</em></p>"
    body = []
    for row in sorted(
        rows,
        key=lambda r: (_METRIC_INDEX.get(str(r.get("metric")), 999), str(r.get("metric"))),
    ):
        if not isinstance(row, dict):
            continue
        m = str(row.get("metric") or "")
        label = METRIC_LABELS.get(m, m)
        st = str(row.get("status") or "OK")
        body.append(
            "<tr>"
            f"<td>{render_status_badge(st)} {escape(label)}</td>"
            f"<td>{escape(str(row.get('baseline')))}</td>"
            f"<td>{escape(str(row.get('current')))}</td>"
            f"<td>{escape(str(row.get('pct_change')))}</td>"
            f"<td>{escape(st)}</td>"
            "</tr>",
        )
    tbl = "<table><thead><tr><th>Metric</th><th>Baseline</th><th>Current</th><th>%Δ</th><th>Status</th></tr></thead><tbody>" + "".join(body) + "</tbody></table>"
    top_html = ""
    if top:
        items = "".join(
            f"<li>{render_status_badge(str(r.get('status')))} {escape(METRIC_LABELS.get(str(r.get('metric')), str(r.get('metric'))))}: "
            f"{escape(str(r.get('pct_change')))}</li>"
            for r in top
            if isinstance(r, dict)
        )
        top_html = "<h3>Top regressions</h3><ul>" + items + "</ul>"
    return head + tbl + top_html


def _render_qualification_section(data: dict[str, Any]) -> str:
    if not data:
        return "<p><em>No qualification report</em></p>"
    qs = str(data.get("qualification_status") or "UNKNOWN")
    head = f"<p>{render_status_badge(qs)} <strong>Decision</strong>: {escape(qs)} release_ready={escape(str(data.get('release_ready')))}</p>"
    checks = data.get("checks") or {}
    rows = []
    if isinstance(checks, dict):
        for name in sorted(checks.keys()):
            block = checks[name] or {}
            st = str(block.get("status") or "UNKNOWN")
            rows.append(
                "<tr><td>" + render_status_badge(st) + f" {escape(name)}</td>"
                f"<td><pre>{escape(json.dumps(block.get('detail'), sort_keys=True, default=str)[:4000])}</pre></td></tr>",
            )
    tbl = "<table><thead><tr><th>Check</th><th>Detail</th></tr></thead><tbody>" + "".join(rows) + "</tbody></table>"
    wf = data.get("warnings") or []
    ff = data.get("failures") or []
    ulw = "<h3>Warnings</h3><ul>" + "".join(f"<li>{escape(str(x))}</li>" for x in sorted(str(x) for x in wf)) + "</ul>" if wf else ""
    ulf = "<h3>Failures</h3><ul>" + "".join(f"<li>{escape(str(x))}</li>" for x in sorted(str(x) for x in ff)) + "</ul>" if ff else ""
    return head + tbl + ulw + ulf


def _render_retention_section(data: dict[str, Any]) -> str:
    if not data:
        return "<p><em>No retention report</em></p>"
    return "<table><tbody>" + "".join(
        f"<tr><th>{escape(str(k))}</th><td>{escape(json.dumps(v, sort_keys=True, default=str))}</td></tr>"
        for k, v in sorted(data.items(), key=lambda kv: str(kv[0]))
    ) + "</tbody></table>"


def _render_artifacts_section(data: dict[str, Any]) -> str:
    inc = data.get("included_files") or []
    miss = data.get("missing_files") or []
    sizes = data.get("artifact_sizes") or {}
    parts = [
        "<table><tbody>",
        f"<tr><th>bundle_version</th><td>{escape(str(data.get('bundle_version')))}</td></tr>",
        f"<tr><th>generated_at (manifest)</th><td>{escape(str(data.get('generated_at')))}</td></tr>",
        "</tbody></table>",
        "<h3>Included files</h3><ul>",
    ]
    parts.extend(f"<li>{escape(str(x))}</li>" for x in inc)
    parts.append("</ul><h3>Missing files</h3><ul>")
    parts.extend(f"<li>{escape(str(x))}</li>" for x in miss)
    parts.append("</ul><h3>Artifact sizes</h3>")
    parts.append(_kv_table(sizes if isinstance(sizes, dict) else {}))
    return "\n".join(parts)


def _render_warnings_section(data: dict[str, Any]) -> str:
    items = data.get("items") or []
    if not items:
        return "<p><em>No input warnings</em></p>"
    return "<ul>" + "".join(f"<li>{escape(str(x))}</li>" for x in sorted(str(x) for x in items)) + "</ul>"


def strict_dashboard_exit_code(payload: dict[str, Any], *, strict: bool) -> int:
    if not strict:
        return 0
    return 1 if bool(payload.get("input_warnings")) else 0
