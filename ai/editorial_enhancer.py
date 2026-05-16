from __future__ import annotations

from typing import Any, Protocol, runtime_checkable


@runtime_checkable
class EditorialEnhancer(Protocol):
    """Optional async LLM layer; handlers never import OpenAI directly."""

    async def enhance_title_suggestions(self, content: str) -> dict[str, str] | None:
        """Return partial keys short_title/standard_title/urgent_title or None to keep heuristics."""


async def apply_optional_title_enhancement(
    enhancer: EditorialEnhancer | None,
    *,
    base: dict[str, str],
    content: str,
) -> dict[str, str]:
    """Merge enhancer output into heuristic titles (Telegram-safe strings)."""
    out = dict(base)
    if enhancer is None:
        return out
    try:
        extra = await enhancer.enhance_title_suggestions(content)
    except Exception:
        return out
    if not extra or not isinstance(extra, dict):
        return out
    for k in ("short_title", "standard_title", "urgent_title"):
        v = extra.get(k)
        if isinstance(v, str) and v.strip():
            out[k] = v.strip()[:500]
    return out
