"""Lightweight JSON + HTML evidence reports (soak, failure drill, benchmark, recovery)."""

from __future__ import annotations

import json
import time
from html import escape
from typing import Any


def _html_page(title: str, body_inner: str) -> str:
    return f"""<!DOCTYPE html>
<html lang="en"><head><meta charset="utf-8"/><title>{escape(title)}</title>
<style>
body {{ font-family: system-ui, sans-serif; margin: 1.25rem; color: #1a1a1a; }}
pre {{ background: #f4f4f5; padding: 0.75rem; overflow: auto; border-radius: 6px; }}
h1 {{ font-size: 1.15rem; }}
.meta {{ color: #555; font-size: 0.9rem; margin-bottom: 1rem; }}
</style></head><body>
<h1>{escape(title)}</h1>
<div class="meta">Generated {escape(time.strftime("%Y-%m-%d %H:%M:%S UTC", time.gmtime()))}</div>
{body_inner}
</body></html>"""


def build_soak_report(payload: dict[str, Any], *, format: str = "json") -> str:
    if format == "json":
        return json.dumps(payload, indent=2, default=str)
    inner = f"<p>Profile: <strong>{escape(str(payload.get('profile')))}</strong></p>"
    inner += f"<p>Ticks: {int(payload.get('ticks') or 0)} duration_sec: {payload.get('duration_sec')}</p>"
    inner += "<h2>Bounded report</h2><pre>" + escape(json.dumps(payload.get("bounded_report"), indent=2, default=str)) + "</pre>"
    if payload.get("warnings"):
        inner += "<h2>Warnings</h2><pre>" + escape(json.dumps(payload["warnings"], indent=2)) + "</pre>"
    return _html_page("Soak test report", inner)


def build_failure_report(payload: dict[str, Any], *, format: str = "json") -> str:
    if format == "json":
        return json.dumps(payload, indent=2, default=str)
    inner = "<pre>" + escape(json.dumps(payload, indent=2, default=str)) + "</pre>"
    return _html_page("Failure simulation report", inner)


def build_recovery_report(payload: dict[str, Any], *, format: str = "json") -> str:
    if format == "json":
        return json.dumps(payload, indent=2, default=str)
    inner = "<pre>" + escape(json.dumps(payload, indent=2, default=str)) + "</pre>"
    return _html_page("Recovery verification report", inner)


def build_runtime_stability_report(payload: dict[str, Any], *, format: str = "json") -> str:
    if format == "json":
        return json.dumps(payload, indent=2, default=str)
    inner = "<pre>" + escape(json.dumps(payload, indent=2, default=str)) + "</pre>"
    return _html_page("Runtime stability / benchmark report", inner)
