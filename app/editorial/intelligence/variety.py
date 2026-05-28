"""Narrative variety — anti-template heuristics."""

from __future__ import annotations

import re
from typing import Any

from app.editorial.intelligence.memory import recent_opener_phrases

_GPT_TEMPLATES = re.compile(
    r"(in a significant development|this comes as|it is worth noting|"
    r"according to reports|experts say|landscape|navigating|delve|"
    r"в знаковом|стоит отметить|по сообщениям|эксперты отмечают|"
    r"на фоне|в контексте)",
    re.I,
)

_HYPE = re.compile(
    r"(game[- ]changer|revolutionary|unprecedented|to the moon|"
    r"революционн|беспрецедент|изменит всё)",
    re.I,
)


def compute_variety_score(
    text: str,
    *,
    runtime_dir: str,
    headline: str = "",
) -> dict[str, Any]:
    body = (text or "").strip()
    warnings: list[str] = []
    score = 0.82

    if _GPT_TEMPLATES.search(body):
        score -= 0.18
        warnings.append("template_phrase")
    if _HYPE.search(body):
        score -= 0.15
        warnings.append("hype_tone")
    sentences = [s.strip() for s in re.split(r"[.!?]\s+", body) if len(s.strip()) > 10]
    if sentences:
        lengths = [len(s) for s in sentences[:4]]
        if len(lengths) >= 2 and max(lengths) - min(lengths) < 15:
            score -= 0.08
            warnings.append("flat_rhythm")
        opener = sentences[0].lower()[:80]
        for recent in recent_opener_phrases(runtime_dir, limit=8):
            if recent and recent[:40] in opener:
                score -= 0.12
                warnings.append("repeated_opener")
                break

    h = (headline or "").strip()
    if h and h.lower() in body.lower()[: len(h) + 20]:
        score -= 0.04
        warnings.append("headline_body_overlap")

    score = max(0.0, min(1.0, score))
    return {
        "variety_score": round(score, 4),
        "warnings": warnings,
        "opener_hint": _suggest_opener_variation(warnings),
    }


def _suggest_opener_variation(warnings: list[str]) -> str:
    if "repeated_opener" in warnings or "template_phrase" in warnings:
        return "Start with the concrete fact or number, not a generic framing sentence."
    if "flat_rhythm" in warnings:
        return "Mix one short punchy sentence with a slightly longer context line."
    return ""


def variety_prompt_addon(runtime_dir: str) -> str:
    """Optional prompt hint for AI (editorial only)."""
    recent = recent_opener_phrases(runtime_dir, limit=5)
    if not recent:
        return ""
    return (
        "Avoid repeating these recent opening patterns: "
        + "; ".join(recent[:3])
        + ". Prefer a fresh, fact-first opener."
    )
