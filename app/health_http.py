"""Minimal asyncio HTTP server for /health, /ready, /ops*, /metrics (optional, HEALTH_HTTP_PORT > 0)."""

from __future__ import annotations

import asyncio
import json
import logging
from typing import Any

from app.ops_http_routes import dispatch_ops_http, parse_query_string

logger = logging.getLogger(__name__)


def _http_response(status: int, body: bytes, content_type: str = "application/json") -> bytes:
    reason = {200: "OK", 403: "Forbidden", 503: "Service Unavailable", 404: "Not Found"}.get(status, "OK")
    header = (
        f"HTTP/1.1 {status} {reason}\r\n"
        f"Content-Type: {content_type}\r\n"
        f"Content-Length: {len(body)}\r\n"
        f"Connection: close\r\n"
        f"\r\n"
    ).encode("ascii")
    return header + body


def _parse_http(raw: bytes) -> tuple[str, str, dict[str, list[str]], dict[str, str]]:
    """Return method, path_only, query_multi, headers_lower."""
    text = raw.decode("utf-8", errors="ignore")
    if not text.strip():
        return "GET", "/", {}, {}
    head, _, body = text.partition("\r\n\r\n")
    lines = head.split("\r\n")
    first = lines[0] if lines else ""
    parts = first.split()
    method = parts[0] if parts else "GET"
    path_full = parts[1] if len(parts) > 1 else "/"
    path_only, _, qs = path_full.partition("?")
    query = parse_query_string(qs)
    hdrs: dict[str, str] = {}
    for ln in lines[1:]:
        if ":" not in ln:
            continue
        k, v = ln.split(":", 1)
        hdrs[k.strip().lower()] = v.strip()
    return method, path_only or "/", query, hdrs


async def _handle_client(
    reader: asyncio.StreamReader,
    writer: asyncio.StreamWriter,
    *,
    settings: Any,
) -> None:
    try:
        raw = await asyncio.wait_for(reader.read(65536), timeout=8.0)
    except Exception:
        writer.close()
        return
    method, path_only, query, headers = _parse_http(raw)

    body_raw = b""
    if "\r\n\r\n" in raw.decode("utf-8", errors="ignore"):
        body_raw = raw.split(b"\r\n\r\n", 1)[-1]

    if method == "POST" and path_only.startswith("/ops/control"):
        try:
            from app.ops_http_routes import ops_token_authorized
            from ops.control.api import dispatch_control_http

            if not ops_token_authorized(settings, query, headers):
                writer.write(_http_response(403, b'{"error":"forbidden"}'))
            else:
                code, ctype, resp_body = await dispatch_control_http(
                    settings, path_only, body_raw=body_raw, headers=headers
                )
                writer.write(_http_response(code, resp_body, content_type=ctype))
        except Exception as exc:
            logger.exception("ops_control failed: %s", exc)
            writer.write(_http_response(500, _e_json(str(exc))))
    elif method != "GET":
        writer.write(_http_response(405, b'{"error":"method_not_allowed"}'))
    elif path_only in ("/health", "/healthz"):
        from app.dependency_state import get_dependency_state

        payload = get_dependency_state().health_payload()
        status = str(payload.get("status") or "healthy")
        http_code = 503 if status == "unhealthy" else 200
        body = json.dumps(payload, separators=(",", ":")).encode("utf-8")
        writer.write(_http_response(http_code, body))
    elif path_only in ("/version", "/version.json"):
        from app.build_provenance import version_payload
        from app.dependency_state import get_dependency_state

        deps = get_dependency_state()
        body = json.dumps(
            version_payload(polling_instance_id=deps.polling_instance_id or ""),
            separators=(",", ":"),
        ).encode("utf-8")
        writer.write(_http_response(200, body))
    elif path_only in ("/ready", "/readiness"):
        from utils.runtime_health import gather_runtime_health

        snap = await gather_runtime_health(settings, include_openai=False)
        body = json.dumps(snap, default=str).encode("utf-8")
        code = 200 if snap.get("ok") else 503
        writer.write(_http_response(code, body))
    else:
        try:
            if path_only.startswith("/runtime"):
                from app.ops_http_routes import ops_token_authorized
                from ops.runtime_api import dispatch_runtime_http

                if not ops_token_authorized(settings, query, headers):
                    writer.write(_http_response(403, b'{"error":"forbidden"}'))
                else:
                    rt = await dispatch_runtime_http(settings, path_only, query=query)
                    if rt is None:
                        writer.write(_http_response(404, b'{"error":"not_found"}'))
                    else:
                        code, ctype, body = rt
                        writer.write(_http_response(code, body, content_type=ctype))
            else:
                ops = await dispatch_ops_http(settings, path_only=path_only, query=query, headers=headers)
                if ops is None:
                    writer.write(_http_response(404, b'{"error":"not_found"}'))
                else:
                    code, ctype, body = ops
                    writer.write(_http_response(code, body, content_type=ctype))
        except Exception as exc:
            logger.exception("ops_http failed: %s", exc)
            writer.write(_http_response(500, _e_json(str(exc))))

    try:
        await writer.drain()
    except Exception:
        pass
    writer.close()
    try:
        await writer.wait_closed()
    except Exception:
        pass


def _e_json(msg: str) -> bytes:
    return json.dumps({"error": "internal", "message": msg[:500]}, separators=(",", ":")).encode("utf-8")


async def serve_health_http(settings: Any) -> asyncio.AbstractServer:
    host = str(getattr(settings, "health_http_bind", "0.0.0.0") or "0.0.0.0")
    port = int(getattr(settings, "health_http_port", 0) or 0)

    async def _cb(reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        await _handle_client(reader, writer, settings=settings)

    server = await asyncio.start_server(_cb, host=host, port=port)
    logger.info("health_http.listening bind=%s port=%s", host, port)
    return server


async def stop_health_server(server: asyncio.AbstractServer | None) -> None:
    if server is None:
        return
    server.close()
    await server.wait_closed()
    logger.info("health_http.stopped")
