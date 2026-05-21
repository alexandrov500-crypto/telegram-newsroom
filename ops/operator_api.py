"""Extended runtime GET routes for audit, analytics, dashboard, transparency."""

from __future__ import annotations

import json
from typing import Any


def _json(obj: Any) -> tuple[int, str, bytes]:
    return 200, "application/json", json.dumps(obj, separators=(",", ":"), default=str).encode("utf-8")


async def dispatch_operator_runtime_http(
    settings: Any,
    path_only: str,
    *,
    query: dict[str, list[str]] | None = None,
) -> tuple[int, str, bytes] | None:
    q = query or {}
    rd = str(getattr(settings, "runtime_state_dir", "var/runtime"))
    p = path_only.rstrip("/")

    def _q(name: str, default: str = "") -> str:
        v = q.get(name)
        return (v[0] if v else default).strip()

    if p == "/runtime/audit/search":
        from ops.audit.search import search_audit

        since = _q("since_unix")
        until = _q("until_unix")
        return _json(
            search_audit(
                rd,
                entity=_q("entity") or None,
                runtime_id=_q("runtime_id") or None,
                source=_q("source") or None,
                topic=_q("topic") or None,
                since_unix=float(since) if since else None,
                until_unix=float(until) if until else None,
                limit=int(_q("limit", "50") or "50"),
                offset=int(_q("offset", "0") or "0"),
            )
        )

    if p == "/runtime/analytics/publication":
        from ops.analytics.publication import publication_analytics_payload

        return _json(publication_analytics_payload(rd, days=int(_q("days", "14") or "14")))

    if p == "/runtime/dashboard/overview":
        from ops.dashboard.payloads import dashboard_overview

        return _json(await dashboard_overview(settings))

    if p == "/runtime/dashboard/editorial":
        from ops.dashboard.payloads import dashboard_editorial

        return _json(await dashboard_editorial(settings))

    if p == "/runtime/dashboard/incidents":
        from ops.dashboard.payloads import dashboard_incidents

        return _json(dashboard_incidents(settings))

    if p == "/runtime/dashboard/publication":
        from ops.dashboard.payloads import dashboard_publication

        return _json(dashboard_publication(settings))

    if p == "/runtime/transparency/export":
        from ops.transparency.export import build_transparency_bundle

        hours = float(_q("hours", "24") or "24")
        return _json(build_transparency_bundle(settings, hours=hours))

    return None
