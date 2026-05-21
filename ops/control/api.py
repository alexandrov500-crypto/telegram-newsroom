"""POST /ops/control/* dispatch."""

from __future__ import annotations

import json
import uuid
from typing import Any

from ops.control.handlers import dispatch_control_action


def _parse_body(raw: bytes) -> dict[str, Any]:
    if not raw:
        return {}
    try:
        data = json.loads(raw.decode("utf-8"))
        return data if isinstance(data, dict) else {}
    except (json.JSONDecodeError, UnicodeDecodeError):
        return {}


def _correlation_id(headers: dict[str, str], body: dict[str, Any]) -> str:
    h = headers.get("x-correlation-id") or headers.get("X-Correlation-ID") or ""
    if h.strip():
        return h.strip()[:64]
    b = str(body.get("correlation_id") or "").strip()
    if b:
        return b[:64]
    return uuid.uuid4().hex[:16]


async def dispatch_control_http(
    settings: Any,
    path_only: str,
    *,
    body_raw: bytes,
    headers: dict[str, str],
) -> tuple[int, str, bytes]:
    sub = path_only.removeprefix("/ops/control").strip("/")
    body = _parse_body(body_raw)
    cid = _correlation_id(headers, body)
    result = dispatch_control_action(settings, sub, body, correlation_id=cid)
    code = 200 if result.get("ok") else 400
    return code, "application/json", json.dumps(result, separators=(",", ":"), default=str).encode("utf-8")
