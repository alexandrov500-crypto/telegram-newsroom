from __future__ import annotations

import re


def _clean_line(s: str) -> str:
    t = re.sub(r"[\r\n\t]+", " ", (s or "").strip())
    t = re.sub(r" {2,}", " ", t)
    return t[:500]


def _first_line(content: str) -> str:
    for ln in (content or "").splitlines():
        s = ln.strip()
        if s:
            return s
    return "Draft"


def generate_title_suggestions(
    content: str,
    *,
    editor_title: str | None = None,
) -> dict[str, str]:
    """
    Deterministic title variants (heuristic-first). Optional async enhancer applied by caller
    via ``ai.editorial_enhancer.apply_optional_title_enhancement``.
    """
    base = (editor_title or "").strip() or _first_line(content)
    base = _clean_line(base) or "Draft"
    short = base if len(base) <= 72 else base[:69].rstrip() + "…"
    standard = base if len(base) <= 140 else base[:137].rstrip() + "…"
    urgent = base
    if not re.search(r"(?i)^(breaking|urgent|alert)\b", urgent):
        urgent = f"BREAKING: {standard}" if len(standard) <= 120 else f"BREAKING: {short}"
    urgent = _clean_line(urgent)[:200]
    return {
        "short_title": short,
        "standard_title": standard,
        "urgent_title": urgent,
    }
