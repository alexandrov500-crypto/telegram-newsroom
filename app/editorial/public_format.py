"""Public channel format consistency — headline, summary, spacing."""

from __future__ import annotations

import re
from dataclasses import dataclass

from app.editorial.cb_brief_format import apply_cb_brief_shape, cb_brief_format_enabled
from app.editorial.tone_engine import apply_newsroom_tone
from app.editorial.tuning_loader import get_editorial_tuning
from publisher.public_renderer import clean_headline


@dataclass(frozen=True)
class PublicFormatResult:
    headline: str
    summary: str
    duplicate_wording: bool
    readability_score: float
    why_it_matters: str


def _headline_max() -> int:
    return get_editorial_tuning().structure.headline_max_chars


def _summary_limits() -> tuple[int, int]:
    s = get_editorial_tuning().structure
    return s.summary_max_lines, s.summary_max_chars


def _readability_min() -> float:
    return get_editorial_tuning().quality_gate.min_readability


def detect_duplicate_wording(headline: str, summary: str) -> bool:
    h = re.sub(r"\W+", " ", (headline or "").lower()).strip()
    s = re.sub(r"\W+", " ", (summary or "").lower()).strip()
    if not h or not s:
        return False
    if h in s or s.startswith(h):
        return True
    hw = set(h.split())
    sw = set(s.split())
    if len(hw) < 4:
        return False
    overlap = len(hw & sw) / len(hw)
    return overlap >= 0.85


def _readability(text: str) -> float:
    t = (text or "").strip()
    if not t:
        return 0.0
    words = re.findall(r"\w+", t)
    if not words:
        return 0.0
    avg_len = sum(len(w) for w in words) / len(words)
    sentences = max(1, len(re.split(r"[.!?]+", t)))
    avg_sent = len(words) / sentences
    score = 1.0
    if avg_len > 14:
        score -= 0.2
    if avg_sent > 28:
        score -= 0.25
    if len(t) > 1200:
        score -= 0.15
    return round(max(0.0, min(1.0, score)), 4)


def compress_summary(text: str, *, max_lines: int | None = None, max_chars: int | None = None) -> str:
    default_lines, default_chars = _summary_limits()
    limit_lines = max_lines if max_lines is not None else default_lines
    limit_chars = max_chars if max_chars is not None else default_chars
    toned = apply_newsroom_tone(text).text
    lines = [ln.strip() for ln in toned.splitlines() if ln.strip()]
    if not lines:
        paras = [p.strip() for p in toned.split("\n\n") if p.strip()]
        lines = paras or [toned.strip()]
    kept = lines[:limit_lines]
    out = "\n\n".join(kept).strip()
    if len(out) > limit_chars:
        from app.publisher.draft_builder import complete_story_text

        out = complete_story_text(out, max_chars=limit_chars)
    return out


def normalize_headline(text: str) -> str:
    t = apply_newsroom_tone(text).text
    t = re.sub(r"^[⚡🔥📌]+\s*", "", t).strip()
    t = re.sub(r"^(BREAKING|СРОЧНО)\s*[:—-]\s*", "", t, flags=re.I).strip()
    return clean_headline(t, max_len=_headline_max())


def format_public_story(
    headline: str,
    summary: str,
    *,
    why_it_matters: str = "",
    include_why: bool | None = None,
    growth_meta: dict | None = None,
) -> PublicFormatResult:
    """Stable public story shape for renderer."""
    from app.editorial.content_quality import strip_dangling_ellipsis
    from app.editorial.public_post_template import normalize_lead_emoji
    from app.growth_layer.format.growth_brief import compose_growth_brief_body, resolve_growth_blocks
    from app.growth_layer.format.profiles import effective_format_profile, use_cb_brief_at_render, use_growth_brief_at_render

    format_profile = effective_format_profile(growth_meta)

    h = normalize_headline(normalize_lead_emoji(headline))
    s = compress_summary(strip_dangling_ellipsis(summary))
    if not s.strip() and headline:
        s = compress_summary(strip_dangling_ellipsis(headline))
        h = ""
    dup = detect_duplicate_wording(h, s)
    if dup and s:
        s = s[len(h) :].lstrip(" .—-\n") if s.lower().startswith(h.lower()) else s
    read = _readability(f"{h}\n{s}")
    from app.editorial.content_quality import is_generic_insight

    why = (why_it_matters or "").strip()
    if why and is_generic_insight(why):
        why = ""
    if include_why is None:
        tuning = get_editorial_tuning()
        include_why = (
            tuning.structure.include_why_it_matters
            and bool(why)
            and read >= _readability_min()
            and len(why) >= 40
        )
    if not include_why:
        why = ""
    elif not use_cb_brief_at_render(format_profile):
        why = compress_summary(why, max_lines=3, max_chars=420)

    if use_growth_brief_at_render(format_profile):
        blocks = resolve_growth_blocks(headline=h, body=s, growth_meta=growth_meta)
        h = blocks.headline or h
        s = compose_growth_brief_body(blocks)
        why = ""
    elif use_cb_brief_at_render(format_profile):
        from app.editorial.subscriber_wire_format import wire_why_block_enabled

        if wire_why_block_enabled():
            # Unified template: why renders as its own «Почему это важно» block.
            h, s = apply_cb_brief_shape(h, s, "")
            why = compress_summary(why, max_lines=2, max_chars=280)
        else:
            h, s = apply_cb_brief_shape(h, s, why)
            why = ""
    return PublicFormatResult(
        headline=h,
        summary=s,
        duplicate_wording=dup,
        readability_score=read,
        why_it_matters=why,
    )
