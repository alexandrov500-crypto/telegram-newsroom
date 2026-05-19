from __future__ import annotations

import json
from html import escape
from typing import Any

from bot.operations.epistemic_monitor import EpistemicStabilityMonitor
from bot.operations.repository import OperationsRepository


def _html_page(title: str, body: str) -> str:
    return f"""<!DOCTYPE html>
<html><head><meta charset="utf-8"><title>{escape(title)}</title>
<style>
body {{ font-family: system-ui, sans-serif; margin: 1.5rem; background: #0f1419; color: #e7e9ea; }}
h1,h2 {{ color: #1d9bf0; }}
.card {{ background: #16202a; border-radius: 8px; padding: 1rem; margin: 1rem 0; }}
pre {{ overflow-x: auto; font-size: 12px; }}
nav a {{ color: #1d9bf0; margin-right: 1rem; }}
table {{ border-collapse: collapse; width: 100%; }}
td, th {{ border: 1px solid #38444d; padding: 0.5rem; text-align: left; }}
</style></head><body>
<nav>
  <a href="/ops/">Home</a>
  <a href="/ops/explorer/replay">Replay</a>
  <a href="/ops/explorer/contradictions">Contradictions</a>
  <a href="/ops/explorer/epistemic">Epistemic</a>
  <a href="/ops/explorer/incidents">Incidents</a>
</nav>
<h1>{escape(title)}</h1>
{body}
</body></html>"""


def mount_ops_routes(app: Any, *, db_path: str, ops_platform: Any | None = None) -> None:
    """Mount operator observability UX on FastAPI app."""
    from fastapi.responses import HTMLResponse, JSONResponse

    repo = OperationsRepository(__import__("pathlib").Path(db_path))
    epistemic_mon = EpistemicStabilityMonitor(repo)

    @app.get("/ops/", response_class=HTMLResponse)
    async def ops_home() -> str:
        readiness = repo.latest_readiness_score()
        burnin = repo.active_burnin()
        body = "<div class='card'><p>Operational intelligence explorers</p><ul>"
        body += "<li><a href='/ops/explorer/replay'>Replay timeline</a></li>"
        body += "<li><a href='/ops/explorer/contradictions'>Contradiction graph</a></li>"
        body += "<li><a href='/ops/explorer/epistemic'>Epistemic drift</a></li>"
        body += "<li><a href='/ops/explorer/incidents'>Incident bundles</a></li>"
        body += "</ul>"
        if readiness:
            body += f"<p>Latest readiness score: <strong>{readiness['staging_score']:.2f}</strong></p>"
        if burnin:
            body += f"<p>Active burn-in: <code>{burnin['run_id']}</code> ({burnin['profile']})</p>"
        body += "</div>"
        return _html_page("Operations", body)

    @app.get("/ops/explorer/replay", response_class=HTMLResponse)
    async def explorer_replay() -> str:
        samples = repo.burnin_samples(repo.active_burnin()["run_id"] if repo.active_burnin() else "", limit=30)
        if not samples and repo.active_burnin():
            samples = []
        rows = ""
        for s in reversed(samples[-20:]):
            m = json.loads(s["metrics_json"])
            rows += f"<tr><td>{escape(s['sample_at'][-19:])}</td><td>{m.get('health_score','')}</td><td>{m.get('queue_backlog','')}</td></tr>"
        body = f"<div class='card'><table><tr><th>Time</th><th>Health</th><th>Backlog</th></tr>{rows or '<tr><td colspan=3>No samples</td></tr>'}</table></div>"
        return _html_page("Replay timeline", body)

    @app.get("/ops/explorer/contradictions", response_class=HTMLResponse)
    async def explorer_contradictions() -> str:
        with repo._connect() as conn:
            try:
                rows = conn.execute(
                    "SELECT contradiction_id, severity, explanation FROM epistemic_contradictions WHERE status='open' LIMIT 25"
                ).fetchall()
            except Exception:
                rows = []
        items = "".join(
            f"<li><strong>{r['contradiction_id']}</strong> ({r['severity']:.2f}): {escape(str(r['explanation'])[:120])}</li>"
            for r in rows
        ) or "<li>No open contradictions</li>"
        body = f"<div class='card'><ul>{items}</ul><p>Minority views preserved in DB.</p></div>"
        return _html_page("Contradictions", body)

    @app.get("/ops/explorer/epistemic", response_class=HTMLResponse)
    async def explorer_epistemic() -> str:
        series = epistemic_mon.timeline_for_explorer()
        rows = ""
        for s in series[-15:]:
            rows += (
                f"<tr><td>{escape(s['snapshot_at'][-19:])}</td>"
                f"<td>{s.get('confidence_mean','')}</td>"
                f"<td>{s.get('open_contradictions','')}</td>"
                f"<td>{s.get('diversity_score','')}</td></tr>"
            )
        body = f"<div class='card'><table><tr><th>At</th><th>Confidence</th><th>Contradictions</th><th>Diversity</th></tr>{rows or '<tr><td colspan=4>No data</td></tr>'}</table></div>"
        return _html_page("Epistemic drift", body)

    @app.get("/ops/explorer/incidents", response_class=HTMLResponse)
    async def explorer_incidents() -> str:
        with repo._connect() as conn:
            rows = conn.execute(
                "SELECT bundle_id, incident_key, status, created_at FROM ops_incident_bundles ORDER BY created_at DESC LIMIT 15"
            ).fetchall()
        items = "".join(
            f"<li><code>{r['bundle_id']}</code> {escape(r['incident_key'])} ({r['status']})</li>" for r in rows
        ) or "<li>No incidents</li>"
        body = f"<div class='card'><ul>{items}</ul></div>"
        return _html_page("Incidents", body)

    @app.get("/ops/api/export", response_class=JSONResponse)
    async def api_export() -> dict:
        if ops_platform is None:
            return {"error": "ops platform not attached"}
        triage = ops_platform.ergonomics.triage_open()
        return {
            "alerts": [{"title": t.title, "category": t.category, "priority": t.priority} for t in triage],
            "readiness": repo.latest_readiness_score(),
        }
