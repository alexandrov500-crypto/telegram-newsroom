"""AST guard: asyncio.create_task only in task_orchestrator."""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]

ALLOWED_FILE = "app/runtime/task_orchestrator.py"

SCAN_DIRS = ("app", "scheduler", "publisher", "workers", "tools", "newsroom")

# Legacy burn-in entry — migrate incrementally
EXEMPT_PREFIXES = (
    "bot/",
)


def _iter_py_files() -> list[Path]:
    out: list[Path] = []
    for d in SCAN_DIRS:
        root = REPO / d
        if not root.is_dir():
            continue
        for p in root.rglob("*.py"):
            rel = str(p.relative_to(REPO)).replace("\\", "/")
            if "/tests/" in rel or p.name.startswith("test_"):
                continue
            if any(rel.startswith(prefix) for prefix in EXEMPT_PREFIXES):
                continue
            out.append(p)
    return out


def _find_create_task_calls(path: Path) -> list[tuple[int, str]]:
    rel = str(path.relative_to(REPO)).replace("\\", "/")
    if rel == ALLOWED_FILE:
        return []
    text = path.read_text(encoding="utf-8", errors="replace")
    try:
        tree = ast.parse(text)
    except SyntaxError:
        return []
    hits: list[tuple[int, str]] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        fn = node.func
        name = None
        if isinstance(fn, ast.Attribute) and fn.attr == "create_task":
            if isinstance(fn.value, ast.Name) and fn.value.id == "asyncio":
                name = "asyncio.create_task"
        if name:
            hits.append((node.lineno, rel))
    return hits


def test_no_raw_asyncio_create_task_outside_orchestrator() -> None:
    violations: list[str] = []
    for path in _iter_py_files():
        for lineno, rel in _find_create_task_calls(path):
            violations.append(f"{rel}:{lineno}")
    assert not violations, (
        "Use app.runtime.task_orchestrator.create_traced_task instead:\n"
        + "\n".join(violations[:40])
    )
