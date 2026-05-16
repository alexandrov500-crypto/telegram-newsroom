from __future__ import annotations

import asyncio
from dataclasses import replace

from app.ops_http_routes import dispatch_ops_http, ops_token_authorized, parse_query_string
from tests.conftest import minimal_test_settings


def test_parse_query_string() -> None:
    q = parse_query_string("a=1&b=two")
    assert q["a"] == ["1"] and q["b"] == ["two"]


def test_ops_token_gate() -> None:
    s = minimal_test_settings()
    assert ops_token_authorized(s, {}, {}) is True
    s2 = replace(s, ops_http_token="sekret")
    assert ops_token_authorized(s2, {}, {}) is False
    assert ops_token_authorized(s2, {"token": ["sekret"]}, {}) is True
    assert ops_token_authorized(s2, {}, {"x-ops-token": "sekret"}) is True


def test_dispatch_ignores_unknown_path() -> None:
    s = minimal_test_settings()

    async def run() -> object:
        return await dispatch_ops_http(s, path_only="/nope", query={}, headers={})

    assert asyncio.run(run()) is None
