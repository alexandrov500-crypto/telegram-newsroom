from __future__ import annotations

import asyncio

from ai.editorial_enhancer import apply_optional_title_enhancement
from ai.editorial_titles import generate_title_suggestions


def test_generate_title_suggestions_basic() -> None:
    out = generate_title_suggestions("First line title\n\nbody", editor_title=None)
    assert set(out.keys()) == {"short_title", "standard_title", "urgent_title"}
    assert "First line title" in out["standard_title"]
    assert out["urgent_title"].lower().startswith("breaking:") or "BREAKING" in out["urgent_title"]


def test_apply_optional_title_enhancement_none() -> None:
    base = generate_title_suggestions("hello world")
    merged = asyncio.run(apply_optional_title_enhancement(None, base=base, content="hello world"))
    assert merged == base
