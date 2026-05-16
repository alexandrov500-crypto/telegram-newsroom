from __future__ import annotations

import asyncio
import importlib.util
from pathlib import Path

from tests.conftest import minimal_test_settings


def _load_runtime_benchmark_module():
    root = Path(__file__).resolve().parents[1]
    path = root / "tools" / "runtime_benchmark.py"
    spec = importlib.util.spec_from_file_location("_runtime_benchmark_cli", path)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_build_benchmark_payload_shape() -> None:
    rb = _load_runtime_benchmark_module()
    s = minimal_test_settings()
    p = rb.build_benchmark_payload(s)
    assert "metrics_export" in p
    assert "editorial_analytics" in p
    assert "derived" in p
    assert "runtime_state_file_bytes" in p
    assert "event_history.json" in p["runtime_state_file_bytes"]


def test_async_main_without_transport_no_crash() -> None:
    rb = _load_runtime_benchmark_module()
    s = minimal_test_settings()
    p = asyncio.run(rb.async_main(s, sample_transport=False))
    assert p.get("transport_sample") is None
