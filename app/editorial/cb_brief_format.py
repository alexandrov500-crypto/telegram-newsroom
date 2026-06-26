"""
Unified public post shape (reference: @cb_economics).

Layout:
  1) Bold headline — one fact, no clickbait, no trailing intrigue
  2) Body — 1–3 short paragraphs (2–5 sentences), last sentence = conclusion
  3) Optional discreet source line (handled by attribution layer)

No separate «Почему это важно», hooks, hashtags, CTAs, or open loops.
"""

from __future__ import annotations

import os
import re

from publisher.public_renderer import clean_headline

_SENTENCE_SPLIT = re.compile(r"(?<=[.!?])\s+")
_INTRIGUE = re.compile(
    r"(…|\.\.\.|продолжение\s+темы|узнай|смотри|читайте\s+далее|stay\s+tuned|"
    r"что\s+будет\s+дальше|подробности\s+—)",
    re.I,
)
_QUESTION_HOOK = re.compile(r"^(?:что|как|почему|зачем|кто)\s+", re.I)
_LEAD_EMOJI = re.compile(r"^[\U0001F300-\U0001FAFF\u2600-\u27BF\uFE0F\u200d]+\s*", re.UNICODE)

CB_BRIEF_HEADLINE_MAX = 120


def _cb_body_max_chars() -> int:
    try:
        from app.editorial.wire_post_format import wire_post_limits

        return wire_post_limits().body_max_chars
    except Exception:
        pass
    try:
        return max(720, int(os.getenv("WIRE_POST_BODY_MAX_CHARS", "1050")))
    except ValueError:
        return 1050


def _cb_max_sentences() -> int:
    try:
        from app.editorial.wire_post_format import wire_post_limits

        return wire_post_limits().max_sentences
    except Exception:
        pass
    try:
        return int(os.getenv("WIRE_POST_MAX_SENTENCES", "6"))
    except ValueError:
        return 6


CB_BRIEF_BODY_MAX_CHARS = _cb_body_max_chars()
CB_BRIEF_MAX_PARAGRAPHS = 3
CB_BRIEF_MAX_SENTENCES = _cb_max_sentences()


def cb_brief_format_enabled() -> bool:
    raw = os.getenv("NEWSROOM_CB_BRIEF_FORMAT", "true").strip().lower()
    return raw in {"1", "true", "yes", "on"}


def normalize_cb_headline(headline: str, *, body_fallback: str = "") -> str:
    h = (headline or "").strip()
    while _LEAD_EMOJI.search(h):
        h = _LEAD_EMOJI.sub("", h, count=1).strip()
    h = re.sub(r"^(BREAKING|СРОЧНО)\s*[:—-]\s*", "", h, flags=re.I).strip()
    h = re.sub(r"^[⚡🔥📌]+\s*", "", h).strip()
    h = _INTRIGUE.sub("", h).strip()
    if not h and body_fallback:
        sents = [s.strip() for s in _SENTENCE_SPLIT.split(body_fallback.strip()) if s.strip()]
        h = sents[0] if sents else body_fallback.strip()[:CB_BRIEF_HEADLINE_MAX]
    h = clean_headline(h, max_len=CB_BRIEF_HEADLINE_MAX)
    if h.endswith(":"):
        h = h[:-1].rstrip()
    if _QUESTION_HOOK.search(h):
        # Prefer declarative headline from body second sentence if available.
        sents = [s.strip() for s in _SENTENCE_SPLIT.split(body_fallback.strip()) if s.strip()]
        if len(sents) > 1:
            h = clean_headline(sents[0], max_len=CB_BRIEF_HEADLINE_MAX)
    return h


def _sentences(text: str) -> list[str]:
    return [s.strip() for s in _SENTENCE_SPLIT.split((text or "").strip()) if len(s.strip()) > 12]


def _finish_sentence(s: str) -> str:
    t = (s or "").strip().rstrip("…")
    if not t:
        return t
    if t[-1] not in ".!?":
        return f"{t}."
    return t


def normalize_cb_body(body: str, *, why_it_matters: str = "", max_chars: int | None = None) -> str:
    limit = max_chars if max_chars is not None else _cb_body_max_chars()
    try:
        from app.editorial.wire_post_format import normalize_wire_body

        return normalize_wire_body(body, why_it_matters=why_it_matters)
    except Exception:
        pass
    t = (body or "").strip()
    t = _INTRIGUE.sub("", t).strip()
    why = (why_it_matters or "").strip()
    if why and why.lower() not in t.lower():
        why_s = _finish_sentence(why)
        if why_s and len(why_s) >= 24:
            t = f"{t.rstrip()} {why_s}".strip() if t else why_s

    sents = _sentences(t)
    if not sents:
        return ""
    sents = sents[:CB_BRIEF_MAX_SENTENCES]
    sents = [_finish_sentence(s) for s in sents]

    # Group into 1–3 paragraphs: 1 sent → 1 para; 2–3 → 2 paras; 4–5 → 3 paras
    if len(sents) <= 1:
        paras = sents
    elif len(sents) <= 3:
        paras = [" ".join(sents[:-1]) if len(sents) > 1 else sents[0], sents[-1]] if len(sents) > 1 else sents
        if len(sents) == 3:
            paras = [sents[0], " ".join(sents[1:])]
        elif len(sents) == 2:
            paras = sents
    else:
        mid = max(1, (len(sents) - 1) // 2)
        paras = [
            " ".join(sents[:mid]),
            " ".join(sents[mid:-1]) if mid < len(sents) - 1 else sents[mid],
            sents[-1],
        ]
        paras = [p for p in paras if p.strip()]

    paras = paras[:CB_BRIEF_MAX_PARAGRAPHS]
    out = "\n\n".join(p.strip() for p in paras if p.strip())
    if len(out) > max_chars:
        from app.publisher.draft_builder import complete_story_text

        out = complete_story_text(out, max_chars=max_chars)
    return out.strip()


def apply_cb_brief_shape(
    headline: str,
    summary: str,
    why_it_matters: str = "",
) -> tuple[str, str]:
    """Return (headline, body) with why folded into body conclusion."""
    body = normalize_cb_body(summary, why_it_matters=why_it_matters)
    h = normalize_cb_headline(headline, body_fallback=body or summary)
    if h and body:
        h_norm = h.lower().strip(" .")
        body_norm = body.lower()
        if body_norm.startswith(h_norm):
            body = body[len(h) :].lstrip(" .—-\n")
            body = normalize_cb_body(body)
    return h, body


def compose_cb_brief_text(text: str, *, max_chars: int = CB_BRIEF_BODY_MAX_CHARS + CB_BRIEF_HEADLINE_MAX) -> str:
    """Polished single block: headline blank line body (for draft builder / fallback)."""
    raw = (text or "").strip()
    if not raw:
        return ""
    lines = [ln.strip() for ln in raw.splitlines() if ln.strip()]
    if len(lines) >= 2 and len(lines[0]) <= CB_BRIEF_HEADLINE_MAX + 20:
        h, b = apply_cb_brief_shape(lines[0], "\n\n".join(lines[1:]))
    else:
        h, b = apply_cb_brief_shape("", raw)
    if h and b:
        out = f"{h}\n\n{b}"
    elif b:
        out = b
    else:
        out = h or raw
    if len(out) > max_chars:
        from app.publisher.draft_builder import complete_story_text

        out = complete_story_text(out, max_chars=max_chars)
    return out.strip()
