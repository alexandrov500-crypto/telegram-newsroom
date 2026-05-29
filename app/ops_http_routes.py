"""Minimal server-rendered ops pages + JSON/metrics (used from asyncio health HTTP)."""

from __future__ import annotations

import html
import json
from typing import Any
from urllib.parse import parse_qs

from app.config import Settings
from db.repository import get_draft_by_id, search_drafts_operational
from db.session import session_scope
from editorial.diffing import format_edit_history, headline_and_lead_diff
from editorial.explanations import (
    explain_cadence_block,
    explain_from_draft_extras,
    explain_suppression,
)
from app.runtime_metrics import export_merged_metrics
from utils.prometheus_export import render_prometheus_metrics

def ops_token_authorized(settings: Settings, query: dict[str, list[str]], headers: dict[str, str]) -> bool:
    tok = (getattr(settings, "ops_http_token", "") or "").strip()
    if not tok:
        return True
    q_t = (query.get("token") or [""])[0].strip()
    h_t = (headers.get("x-ops-token") or headers.get("X-Ops-Token") or "").strip()
    return q_t == tok or h_t == tok


def _e(x: Any) -> str:
    return html.escape(str(x), quote=True)


def _nav() -> str:
    return (
        "<nav style=\"margin:8px 0;font-size:14px\">"
        "<a href=\"/ops\">overview</a> · <a href=\"/ops/search\">search</a> · "
        "<a href=\"/ops/newsroom-intel\">newsroom-intel</a> · "
        "<a href=\"/ops/dlq\">dlq</a> · <a href=\"/runtime/status\">runtime</a> · "
        "<a href=\"/runtime/timeline\">timeline</a> · "
        "<a href=\"/ops.json\">bundle.json</a> · "
        "<a href=\"/metrics\">metrics</a></nav>"
    )


async def _bundle_dict(settings: Settings) -> dict[str, Any]:
    from dashboard import build_operational_dashboard_bundle

    b = await build_operational_dashboard_bundle(settings, include_openai=False)
    out = b.to_dict()
    try:
        from app.observability.newsroom_ops import newsroom_ops_snapshot

        from app.observability.newsroom_ops import launch_dashboard

        out["newsroom_ops"] = launch_dashboard(runtime_dir=settings.runtime_state_dir)
    except Exception:
        pass
    return out


async def _dlq_page_html(settings: Settings) -> str:
    from worker.job_queue import JobKind
    from worker.reliable_transport import get_reliable_transport

    rows_html: list[str] = ["<h2>DLQ (newest samples)</h2>"]
    try:
        transport = get_reliable_transport()
    except Exception as exc:
        return "<p>DLQ unavailable (reliable transport not initialized): " + _e(repr(exc)) + "</p>"

    for k in JobKind:
        try:
            recs = await transport.list_dlq(k, limit=8)
        except Exception as exc:
            rows_html.append(f"<h3>{_e(k.value)}</h3><p>{_e(repr(exc))}</p>")
            continue
        rows_html.append(f"<h3>{_e(k.value)}</h3><table><tr><th>terminal</th><th>reason</th><th>delivery</th></tr>")
        for r in recs:
            if not isinstance(r, dict):
                continue
            rows_html.append(
                "<tr><td>"
                + _e(r.get("terminal"))
                + "</td><td>"
                + _e((r.get("reason") or "")[:240])
                + "</td><td><code>"
                + _e(r.get("delivery_id"))
                + "</code></td></tr>"
            )
        rows_html.append("</table>")
    return "".join(rows_html)


async def _draft_page_html(settings: Settings, draft_id: int) -> str:
    async with session_scope() as session:
        d = await get_draft_by_id(session, draft_id)
    if d is None:
        return "<p>Draft not found.</p>"
    try:
        ex = json.loads(d.draft_extras or "{}")
    except json.JSONDecodeError:
        ex = {}
    exp = explain_from_draft_extras(ex if isinstance(ex, dict) else {})
    dif = headline_and_lead_diff(
        draft_content=d.content or "",
        editor_title=d.editor_title,
        editor_summary=d.editor_summary,
    )
    hist_txt = format_edit_history(getattr(d, "edit_history", None) or "[]")
    body_head = (d.content or "").splitlines()[0][:180] if (d.content or "").splitlines() else ""
    links = (
        f"<p><a href=\"/ops/why/{draft_id}/suppressed\">why suppressed</a> · "
        f"<a href=\"/ops/why/{draft_id}/escalated\">why escalated</a> · "
        f"<a href=\"/ops/why/{draft_id}/relevance\">relevance</a> · "
        f"<a href=\"/ops/trace/{draft_id}/policy\">policy trace</a> · "
        f"<a href=\"/ops/trace/{draft_id}/cadence\">cadence trace</a> · "
        f"<a href=\"/ops/breakdown/{draft_id}\">decision breakdown</a></p>"
    )
    return (
        f"<h2>Draft #{draft_id}</h2>"
        + links
        + "<p><b>status</b> "
        + _e(d.status)
        + " · <b>head</b> "
        + _e(body_head)
        + "</p>"
        + "<h3>Concise explanation</h3>"
        + (exp.get("concise_html") or "")
        + "<h3>Detailed explanation</h3>"
        + (exp.get("detailed_html") or "")
        + "<h3>Headline / lead diff (heuristic)</h3><pre>"
        + _e((dif.get("title_diff") or "") + "\n" + (dif.get("summary_diff") or ""))
        + "</pre>"
        + "<h3>Moderation edit history</h3><pre>"
        + _e(hist_txt[:8000])
        + "</pre>"
    )


def _extras_dict(draft_extras_json: str) -> dict[str, Any]:
    try:
        o = json.loads(draft_extras_json or "{}")
        return o if isinstance(o, dict) else {}
    except json.JSONDecodeError:
        return {}


async def _why_page(settings: Settings, draft_id: int, aspect: str) -> str:
    async with session_scope() as session:
        d = await get_draft_by_id(session, draft_id)
    if d is None:
        return "<p>Draft not found.</p>"
    ex = _extras_dict(d.draft_extras or "{}")
    ci = ex.get("cluster_intelligence") or {}
    pd = ci.get("pipeline_decision") or {}
    ep = pd.get("editorial_pipeline") or {}
    rel = pd.get("relevance") or {}
    esc = bool(ex.get("editorial_escalate")) or bool(pd.get("escalate_priority"))
    total = rel.get("total")

    if aspect == "suppressed":
        return "<pre>" + _e(explain_suppression(ex)) + "</pre>"
    if aspect == "escalated":
        msg = (
            "Escalation flag is ON for this draft (editorial_escalate or pipeline escalate)."
            if esc
            else "No escalation flag on this draft."
        )
        return "<p>" + _e(msg) + "</p><pre>" + _e(json.dumps(ep, indent=2, default=str)[:8000]) + "</pre>"
    if aspect == "relevance":
        return (
            "<p>Relevance total: "
            + _e(total)
            + "</p><pre>"
            + _e(json.dumps(rel, indent=2, default=str)[:12000])
            + "</pre>"
        )
    return "<p>Unknown aspect.</p>"


async def _trace_page(settings: Settings, draft_id: int, kind: str) -> str:
    async with session_scope() as session:
        d = await get_draft_by_id(session, draft_id)
    if d is None:
        return "<p>Draft not found.</p>"
    ex = _extras_dict(d.draft_extras or "{}")
    ci = ex.get("cluster_intelligence") or {}
    pd = ci.get("pipeline_decision") or {}
    rel = pd.get("relevance") or {}
    pubi = ex.get("publication_intel") or {}
    if kind == "policy":
        notes = list(rel.get("policy_notes") or [])
        block = "<h3>Policy notes</h3><ul>" + "".join(f"<li>{_e(n)}</li>" for n in notes) + "</ul>"
        block += "<h3>pipeline_decision (raw)</h3><pre>" + _e(json.dumps(pd, indent=2, default=str)[:16000]) + "</pre>"
        return block
    if kind == "cadence":
        gate = (pubi.get("cadence_gate_preview") or {}) if isinstance(pubi, dict) else {}
        reasons = list(gate.get("reasons") or [])
        return "<h3>Cadence gate preview (at draft build)</h3><pre>" + _e(explain_cadence_block(reasons)) + "</pre><pre>" + _e(
            json.dumps(gate, indent=2, default=str)[:8000]
        ) + "</pre>"
    return "<p>Unknown trace kind.</p>"


async def _breakdown_page(settings: Settings, draft_id: int) -> str:
    async with session_scope() as session:
        d = await get_draft_by_id(session, draft_id)
    if d is None:
        return "<p>Draft not found.</p>"
    ex = _extras_dict(d.draft_extras or "{}")
    exp = explain_from_draft_extras(ex)
    structured = exp.get("structured") or {}
    return "<h3>Structured breakdown</h3><pre>" + _e(json.dumps(structured, indent=2, default=str)[:12000]) + "</pre>"


async def _search_page_html(settings: Settings, query: dict[str, list[str]]) -> str:
    def g(name: str) -> str:
        v = query.get(name)
        return (v[0] or "").strip() if v else ""

    topic = g("topic")
    entity = g("entity")
    fp = g("fingerprint")
    sup = g("suppression")
    status = g("status")
    form = (
        "<form method=\"get\" action=\"/ops/search\">"
        "<label>topic <input name=\"topic\" value=\""
        + _e(topic)
        + "\"></label> "
        "<label>entity <input name=\"entity\" value=\""
        + _e(entity)
        + "\"></label> "
        "<label>fingerprint <input name=\"fingerprint\" value=\""
        + _e(fp)
        + "\"></label><br>"
        "<label>suppression <input name=\"suppression\" value=\""
        + _e(sup)
        + "\"></label> "
        "<label>status <input name=\"status\" value=\""
        + _e(status)
        + "\"></label> "
        "<button type=\"submit\">Search</button></form>"
    )
    if not any([topic, entity, fp, sup, status]):
        return "<h2>Search drafts</h2>" + form + "<p>Enter at least one filter.</p>"

    async with session_scope() as session:
        hits = await search_drafts_operational(
            session,
            topic_substr=topic or None,
            entity_substr=entity or None,
            fingerprint_substr=fp or None,
            suppression_reason_substr=sup or None,
            status=status or None,
            limit=40,
        )
    lines = ["<h2>Results</h2>", form, "<table><tr><th>id</th><th>status</th><th>preview</th></tr>"]
    for d in hits:
        head = (d.content or "").splitlines()[0][:120] if (d.content or "").splitlines() else ""
        lines.append(
            "<tr><td><a href=\"/ops/draft/"
            + _e(d.id)
            + "\">"
            + _e(d.id)
            + "</a></td><td>"
            + _e(d.status)
            + "</td><td>"
            + _e(head)
            + "</td></tr>"
        )
    lines.append("</table>")
    return "".join(lines)


async def _index_html(settings: Settings) -> str:
    bundle = await _bundle_dict(settings)
    rt = bundle.get("runtime") or {}
    health = rt.get("health") or {}
    checks = health.get("checks") or {}
    qdepth = (checks.get("queues") or {}).get("depth_by_kind") or {}
    parts = [
        "<h2>Runtime</h2>",
        "<p>readiness ok="
        + _e(health.get("ok"))
        + "</p>",
        "<h3>Queue depth</h3><pre>"
        + _e(json.dumps(qdepth, indent=2))
        + "</pre>",
        "<h2>Editorial intelligence (summary)</h2><pre>"
        + _e(json.dumps(bundle.get("editorial"), indent=2, default=str)[:24_000])
        + "</pre>",
        "<h2>Operational analytics</h2><pre>"
        + _e(json.dumps(bundle.get("editorial_operational"), indent=2, default=str))
        + "</pre>",
    ]
    warns = bundle.get("warnings") or []
    if warns:
        parts.append("<h2>Warnings</h2><ul>")
        for w in warns:
            if isinstance(w, dict):
                parts.append("<li>" + _e(w.get("code")) + ": " + _e(w.get("message")) + "</li>")
        parts.append("</ul>")
    tl = bundle.get("timeline_tail") or []
    if tl:
        parts.append("<h2>Recent timeline</h2><table><tr><th>ts</th><th>kind</th></tr>")
        for row in tl[:20]:
            if isinstance(row, dict):
                parts.append("<tr><td>" + _e(row.get("ts")) + "</td><td>" + _e(row.get("kind")) + "</td></tr>")
        parts.append("</table>")
    return "".join(parts)


async def dispatch_ops_http(
    settings: Settings,
    *,
    path_only: str,
    query: dict[str, list[str]],
    headers: dict[str, str],
) -> tuple[int, str, bytes] | None:
    """
    Handle /ops*, /ops.json, /metrics.
    Returns (status, content_type, body) or None if this module should not handle the path.
    """
    p = path_only.split("?", 1)[0].rstrip("/") or "/"
    if p == "/ops.json":
        if not ops_token_authorized(settings, query, headers):
            return 403, "application/json", b'{"error":"forbidden"}'
        b = await _bundle_dict(settings)
        raw = json.dumps(b, indent=2, default=str).encode("utf-8")
        return 200, "application/json", raw

    if p == "/metrics":
        if not ops_token_authorized(settings, query, headers):
            return 403, "text/plain", b"forbidden\n"
        body = render_prometheus_metrics(export_merged_metrics()).encode("utf-8")
        return 200, "text/plain; charset=utf-8", body

    if p == "/ops" or p.startswith("/ops/"):
        if not ops_token_authorized(settings, query, headers):
            return 403, "text/html; charset=utf-8", b"<p>Forbidden</p>"

        if p == "/ops":
            html_page = "<!DOCTYPE html><html><head><meta charset=\"utf-8\"><title>ops</title></head><body>" + _nav() + await _index_html(
                settings
            ) + "</body></html>"
            return 200, "text/html; charset=utf-8", html_page.encode("utf-8")

        segs = [x for x in p.split("/") if x]
        # ['ops', ...]
        if len(segs) >= 2 and segs[1] == "search":
            page = "<!DOCTYPE html><html><head><meta charset=\"utf-8\"><title>search</title></head><body>" + _nav() + await _search_page_html(
                settings, query
            ) + "</body></html>"
            return 200, "text/html; charset=utf-8", page.encode("utf-8")

        if len(segs) >= 2 and segs[1] in ("newsroom-intel", "newsroom-intel.json"):
            bundle = await _bundle_dict(settings)
            editorial = bundle.get("editorial") or {}
            intel = (
                editorial.get("operator_observability")
                if isinstance(editorial, dict)
                else {}
            ) or {}
            want_json = segs[1] == "newsroom-intel.json" or query.get("format") == ["json"]
            if want_json:
                raw = json.dumps(intel, indent=2, default=str).encode("utf-8")
                return 200, "application/json", raw
            page = (
                "<!DOCTYPE html><html><head><meta charset=\"utf-8\"><title>newsroom-intel</title></head><body>"
                + _nav()
                + "<h2>Newsroom intelligence</h2><pre>"
                + _e(json.dumps(intel, indent=2, default=str)[:48_000])
                + "</pre></body></html>"
            )
            return 200, "text/html; charset=utf-8", page.encode("utf-8")

        if len(segs) >= 2 and (segs[1] == "panel" or segs[1].startswith("panel") or segs[1] == "operator"):
            from app.reliability.operator_summary import build_operator_summary

            summary = await build_operator_summary(settings)
            want_json = segs[1] in ("panel.json",) or query.get("format") == ["json"]
            if want_json:
                raw = json.dumps(summary, indent=2, default=str).encode("utf-8")
                return 200, "application/json", raw
            rows = []
            for k, v in summary.items():
                if isinstance(v, dict):
                    rows.append(f"<tr><th colspan=2>{_e(k)}</th></tr>")
                    for sk, sv in v.items():
                        rows.append(f"<tr><td>{_e(sk)}</td><td><pre>{_e(sv)}</pre></td></tr>")
                else:
                    rows.append(f"<tr><td>{_e(k)}</td><td>{_e(v)}</td></tr>")
            page = (
                "<!DOCTYPE html><html><head><meta charset=\"utf-8\"><title>operator</title></head><body>"
                + _nav()
                + "<h1>Operator panel</h1><table>"
                + "".join(rows)
                + "</table></body></html>"
            )
            return 200, "text/html; charset=utf-8", page.encode("utf-8")

        if len(segs) >= 2 and segs[1] == "dlq":
            page = "<!DOCTYPE html><html><head><meta charset=\"utf-8\"><title>dlq</title></head><body>" + _nav() + await _dlq_page_html(
                settings
            ) + "</body></html>"
            return 200, "text/html; charset=utf-8", page.encode("utf-8")

        if len(segs) == 3 and segs[1] == "draft" and segs[2].isdigit():
            did = int(segs[2])
            page = (
                "<!DOCTYPE html><html><head><meta charset=\"utf-8\"><title>draft</title></head><body>"
                + _nav()
                + await _draft_page_html(settings, did)
                + "</body></html>"
            )
            return 200, "text/html; charset=utf-8", page.encode("utf-8")

        if len(segs) == 4 and segs[1] == "why" and segs[2].isdigit() and segs[3] in ("suppressed", "escalated", "relevance"):
            did = int(segs[2])
            page = (
                "<!DOCTYPE html><html><head><meta charset=\"utf-8\"><title>why</title></head><body>"
                + _nav()
                + await _why_page(settings, did, segs[3])
                + "</body></html>"
            )
            return 200, "text/html; charset=utf-8", page.encode("utf-8")

        if len(segs) == 4 and segs[1] == "trace" and segs[2].isdigit() and segs[3] in ("policy", "cadence"):
            did = int(segs[2])
            page = (
                "<!DOCTYPE html><html><head><meta charset=\"utf-8\"><title>trace</title></head><body>"
                + _nav()
                + await _trace_page(settings, did, segs[3])
                + "</body></html>"
            )
            return 200, "text/html; charset=utf-8", page.encode("utf-8")

        if len(segs) == 3 and segs[1] == "breakdown" and segs[2].isdigit():
            did = int(segs[2])
            page = (
                "<!DOCTYPE html><html><head><meta charset=\"utf-8\"><title>breakdown</title></head><body>"
                + _nav()
                + await _breakdown_page(settings, did)
                + "</body></html>"
            )
            return 200, "text/html; charset=utf-8", page.encode("utf-8")

        return 404, "text/html; charset=utf-8", b"<p>Not found</p>"

    return None


def parse_query_string(qs: str) -> dict[str, list[str]]:
    if not qs:
        return {}
    return parse_qs(qs, keep_blank_values=False)
