from __future__ import annotations

from app.health_http import _http_response


def test_http_response_headers() -> None:
    body = b'{"a":1}'
    raw = _http_response(200, body)
    assert b"HTTP/1.1 200" in raw
    assert b"Content-Length: 7" in raw
    assert raw.endswith(body)
