"""Static guard: no direct imports of protected *_impl symbols."""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]

FORBIDDEN_IMPORTS = frozenset(
    {
        "_summarize_step_impl",
        "_scheduled_publish_step_impl",
        "_execute_admin_publication_flow_impl",
        "_try_minimal_draft_from_raw_impl",
    }
)

ALLOWED_IMPORT_FILES = frozenset(
    {
        "scheduler/jobs.py",
        "publisher/publish_service.py",
        "app/recovery/minimal_draft.py",
    }
)

SCAN_DIRS = ("app", "scheduler", "publisher", "workers", "tools", "bot", "newsroom")


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
            out.append(p)
    return out


def _forbidden_imports_in_file(path: Path) -> list[str]:
    rel = str(path.relative_to(REPO)).replace("\\", "/")
    if rel in ALLOWED_IMPORT_FILES:
        return []
    try:
        tree = ast.parse(path.read_text(encoding="utf-8", errors="replace"))
    except SyntaxError:
        return []
    hits: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            for alias in node.names:
                if alias.name in FORBIDDEN_IMPORTS:
                    hits.append(f"{rel}:import_from {alias.name}")
        elif isinstance(node, ast.Import):
            for alias in node.names:
                base = alias.asname or alias.name
                if base in FORBIDDEN_IMPORTS:
                    hits.append(f"{rel}:import {base}")
    # from x import y where y is impl
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            mod = node.module or ""
            for alias in node.names:
                name = alias.name
                if name in FORBIDDEN_IMPORTS:
                    hits.append(f"{rel}:from {mod} import {name}")
    return hits


def test_no_direct_impl_imports() -> None:
    violations: list[str] = []
    for path in _iter_py_files():
        violations.extend(_forbidden_imports_in_file(path))
    assert not violations, "Direct impl imports forbidden:\n" + "\n".join(violations[:40])
