"""Ensure protected pipeline implementations are not called without the wrapper."""

from __future__ import annotations

import ast
import re
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]

PROTECTED_IMPLS = {
    "_summarize_step_impl",
    "_execute_admin_publication_flow_impl",
    "_try_minimal_draft_from_raw_impl",
    "_scheduled_publish_step_impl",
}

# Implementations may only be referenced from their wrapper host file.
IMPL_HOST_FILE = {
    "_summarize_step_impl": "scheduler/jobs.py",
    "_scheduled_publish_step_impl": "scheduler/jobs.py",
    "_execute_admin_publication_flow_impl": "publisher/publish_service.py",
    "_try_minimal_draft_from_raw_impl": "app/recovery/minimal_draft.py",
}

SCAN_DIRS = ("scheduler", "publisher", "app", "tools", "workers", "bot")


def _py_files() -> list[Path]:
    out: list[Path] = []
    for d in SCAN_DIRS:
        root = REPO / d
        if not root.is_dir():
            continue
        for p in root.rglob("*.py"):
            if "test_" in p.name or p.name.startswith("test"):
                continue
            out.append(p)
    return out


def _find_calls(path: Path) -> list[tuple[str, int, str]]:
    text = path.read_text(encoding="utf-8", errors="replace")
    try:
        tree = ast.parse(text)
    except SyntaxError:
        return []
    hits: list[tuple[str, int, str]] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            fn = node.func
            name = None
            if isinstance(fn, ast.Name):
                name = fn.id
            elif isinstance(fn, ast.Attribute):
                name = fn.attr
            if name in PROTECTED_IMPLS:
                hits.append((name, node.lineno, str(path.relative_to(REPO))))
    return hits


def test_protected_impls_only_called_via_wrapper() -> None:
    violations: list[str] = []
    for path in _py_files():
        for name, lineno, rel in _find_calls(path):
            line = path.read_text(encoding="utf-8", errors="replace").splitlines()[lineno - 1]
            if line.strip().startswith(f"async def {name}") or line.strip().startswith(f"def {name}"):
                continue
            host = IMPL_HOST_FILE.get(name)
            if host and rel.replace("\\", "/") == host:
                continue
            violations.append(f"{rel}:{lineno} external call to {name}")
    assert not violations, "Bypass paths:\n" + "\n".join(violations[:30])


def test_wrapper_module_exports_execute_pipeline_step() -> None:
    from app.state import pipeline_execution_wrapper as w

    assert hasattr(w, "execute_pipeline_step")
    assert hasattr(w, "require_pipeline_wrapper_active")


def test_bypass_strict_raises() -> None:
    from app.state.pipeline_execution_wrapper import (
        pipeline_evaluation_only,
        require_pipeline_wrapper_active,
    )

    with pipeline_evaluation_only():
        require_pipeline_wrapper_active("test_callee")
        return
    with pytest.raises(RuntimeError, match="PIPELINE BYPASS DETECTED"):
        import os

        os.environ["PIPELINE_BYPASS_STRICT"] = "true"
        try:
            require_pipeline_wrapper_active("test_callee")
        finally:
            os.environ.pop("PIPELINE_BYPASS_STRICT", None)


def test_execute_pipeline_step_emits_trace(monkeypatch: pytest.MonkeyPatch) -> None:
    from app.dependency_state import reset_dependency_state
    from app.openai_circuit import reset_openai_circuit_for_tests
    from app.state.pipeline_execution_wrapper import execute_pipeline_step
    from scheduler.runtime_context import PipelineContext
    from tests.conftest import minimal_test_settings
    from unittest.mock import MagicMock

    reset_dependency_state()
    reset_openai_circuit_for_tests()
    traces: list[str] = []

    def _capture(logger, event, **kw):
        if event == "PIPELINE_EXECUTION_TRACE":
            traces.append(kw.get("phase", ""))

    monkeypatch.setattr(
        "app.state.pipeline_execution_wrapper.log_event",
        _capture,
    )
    ctx = PipelineContext(
        settings=minimal_test_settings(),
        bot=MagicMock(),
        openai=MagicMock(),
    )

    async def _noop():
        return "ok"

    import asyncio

    asyncio.run(execute_pipeline_step(ctx, "collect", _noop, require_should_execute=False))
    assert "wrapper_entry" in traces
    assert "wrapper_exit" in traces
