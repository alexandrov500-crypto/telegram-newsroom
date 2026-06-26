"""
Unified Wire Post — single channel format (synthesis: @cb_economics, @thebell_io, @rbc_news).

Structure (every publish):
  1. Headline — one declarative fact (bold in HTML), no clickbait, no «…»
  2. Lead — what happened (1–2 sentences)
  3. Context — mechanism / background (1–2 sentences)
  4. Close — one finished concluding sentence (market / policy implication)

Rules:
  - Complete thoughts only — no trailing ellipsis, colons, or conjunctions
  - 4–6 sentences in body when source material allows
  - 550–1050 characters in body (wire beat); never ship a headline-only stub
  - Source line is separate (attribution layer), never inside body
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass

_SENTENCE_SPLIT = re.compile(r"(?<=[.!?])\s+")
_INTRIGUE = re.compile(
    r"(…|\.\.\.|продолжение\s+темы|узнай|смотри|читайте\s+далее|stay\s+tuned|"
    r"что\s+будет\s+дальше|подробности\s+—)",
    re.I,
)
_DANGLING_END = re.compile(
    r"[\s,;:–—-]*\b(и|или|а|но|потому что|поскольку|так как|что|чтобы)\s*$",
    re.I,
)
_CONCLUSION_MARKERS = re.compile(
    r"(это\s+значит|означает|повлияет|сдвинет|усилит|снизит|ожидают|прогнозируют|"
    r"риск|ставк|инфляц|рынк|инвестор|регулятор|итог|в\s+итоге)",
    re.I,
)


@dataclass(frozen=True)
class WirePostLimits:
    headline_max: int
    body_max_chars: int
    body_min_chars: int
    max_sentences: int
    min_sentences: int
    target_body_chars: tuple[int, int]


def wire_post_limits() -> WirePostLimits:
    try:
        body_max = int(os.getenv("WIRE_POST_BODY_MAX_CHARS", "1050"))
    except ValueError:
        body_max = 1050
    try:
        body_min = int(os.getenv("WIRE_POST_MIN_BODY_CHARS", "280"))
    except ValueError:
        body_min = 280
    try:
        max_sents = int(os.getenv("WIRE_POST_MAX_SENTENCES", "6"))
    except ValueError:
        max_sents = 6
    try:
        min_sents = int(os.getenv("WIRE_POST_MIN_SENTENCES", "3"))
    except ValueError:
        min_sents = 3
    try:
        target_lo = int(os.getenv("WIRE_POST_TARGET_CHARS_MIN", "520"))
    except ValueError:
        target_lo = 520
    try:
        target_hi = int(os.getenv("WIRE_POST_TARGET_CHARS_MAX", "980"))
    except ValueError:
        target_hi = 980
    return WirePostLimits(
        headline_max=120,
        body_max_chars=max(600, min(body_max, 2000)),
        body_min_chars=max(120, min(body_min, 800)),
        max_sentences=max(4, min(max_sents, 8)),
        min_sentences=max(2, min(min_sents, 6)),
        target_body_chars=(target_lo, min(target_hi, body_max)),
    )


def _sentences(text: str) -> list[str]:
    return [s.strip() for s in _SENTENCE_SPLIT.split((text or "").strip()) if len(s.strip()) > 12]


def finish_sentence(s: str) -> str:
    t = (s or "").strip().rstrip("…").rstrip(".")
    if not t:
        return t
    if t[-1] not in ".!?":
        return f"{t}."
    return t


def ensure_complete_ending(text: str) -> str:
    """Drop dangling clause openers; close with a period."""
    from app.publisher.draft_builder import _finish_thought

    t = _finish_thought((text or "").strip())
    t = _INTRIGUE.sub("", t).strip()
    t = re.sub(r"(\.\.\.|…)$", "", t).rstrip()
    t = _DANGLING_END.sub("", t).rstrip()
    if t and t[-1] not in ".!?":
        t = f"{t}."
    return t


def _has_conclusion(sentences: list[str]) -> bool:
    if not sentences:
        return False
    return bool(_CONCLUSION_MARKERS.search(sentences[-1]))


def normalize_wire_body(
    body: str,
    *,
    why_it_matters: str = "",
    source_sentence_count: int | None = None,
) -> str:
    """
    Shape body into lead + context + close; keep complete sentences up to wire limits.
    """
    from app.publisher.draft_builder import complete_story_text

    limits = wire_post_limits()
    t = _INTRIGUE.sub("", (body or "").strip()).strip()
    why = (why_it_matters or "").strip()
    if why and why.lower() not in t.lower() and len(why) >= 24:
        why_s = finish_sentence(why)
        t = f"{t.rstrip()} {why_s}".strip() if t else why_s

    sents = _sentences(t)
    if not sents:
        return ""

    avail = source_sentence_count if source_sentence_count is not None else len(sents)
    want_min = limits.min_sentences if avail >= limits.min_sentences else min(avail, len(sents))
    want_min = max(2, min(want_min, limits.max_sentences))

    if len(sents) > limits.max_sentences:
        sents = sents[: limits.max_sentences]
    elif len(sents) < want_min and avail >= want_min:
        pass  # keep what we have — AI/fallback may be short; don't pad

    sents = [finish_sentence(s) for s in sents]

    if len(sents) >= 3 and not _has_conclusion(sents):
        last = sents[-1]
        if len(last) < 40 and len(sents) >= 2:
            sents = sents[:-1]

    if len(sents) <= 1:
        paras = sents
    elif len(sents) == 2:
        paras = sents
    elif len(sents) <= 4:
        mid = 1 if len(sents) == 3 else 2
        paras = [" ".join(sents[:mid]), " ".join(sents[mid:])]
    else:
        third = max(1, len(sents) // 3)
        paras = [
            " ".join(sents[:third]),
            " ".join(sents[third : 2 * third]),
            " ".join(sents[2 * third :]),
        ]
    paras = [p.strip() for p in paras if p.strip()]

    out = "\n\n".join(paras)
    out = ensure_complete_ending(out)

    if len(out) > limits.body_max_chars:
        out = complete_story_text(out, max_chars=limits.body_max_chars)
        out = ensure_complete_ending(out)

    if len(out) < limits.body_min_chars and len(t) >= limits.body_min_chars:
        out = complete_story_text(t, max_chars=limits.body_max_chars)
        out = ensure_complete_ending(out)

    return out.strip()


def ai_post_char_range() -> tuple[int, int]:
    lo, hi = wire_post_limits().target_body_chars
    return lo, hi


def wire_post_env_defaults() -> dict[str, str]:
    return {
        "WIRE_POST_BODY_MAX_CHARS": "1050",
        "WIRE_POST_MIN_BODY_CHARS": "280",
        "WIRE_POST_MAX_SENTENCES": "6",
        "WIRE_POST_MIN_SENTENCES": "4",
        "WIRE_POST_TARGET_CHARS_MIN": "520",
        "WIRE_POST_TARGET_CHARS_MAX": "980",
        "WIRE_POST_INTEGRATED_CLOSURE": "true",
    }
