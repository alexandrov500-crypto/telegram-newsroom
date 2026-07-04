"""Normalize raw Telegram source copy into wire-ready text before fallback publish."""

from __future__ import annotations

import re

_SENTENCE_SPLIT = re.compile(r"(?<=[.!?])\s+")
_LEAD_EMOJI = re.compile(r"^[\U0001F300-\U0001FAFF\u2600-\u27BF\uFE0F\u200d☀⚡🔥📌]+\s*", re.UNICODE)
_SOURCE_LABEL = re.compile(
    r"^(?:что\s+происходит|почему\s+(?:это\s+)?важно|что\s+это\s+значит|что\s+будет\s+дальше|"
    r"контекст|итог|вывод)\s*:\s*",
    re.I | re.M,
)
_INLINE_LABEL = re.compile(
    r"(?:^|\n)\s*(?:что\s+происходит|почему\s+(?:это\s+)?важно)\s*:\s*",
    re.I,
)
_SLASH_INITIATIVE = re.compile(r"\s*/\s*Инициатив[а-яё]*[^.!?]*[.!?]?\s*", re.I)
_RBC_TV_WRAP = re.compile(
    r"главные\s+новости\s*[—–-]\s*в\s+утреннем\s+выпуске\s+на\s+телеканале\s+рбк\s*:?",
    re.I,
)
_TIMESTAMP_BULLET = re.compile(
    r"^\s*(?:▪\s*)?\d{1,2}:\d{2}\s*-\s*\d{1,2}:\d{2}\s*[—–-]\s*",
    re.I,
)
_INLINE_TIMESTAMP = re.compile(
    r"▪\s*\d{1,2}:\d{2}\s*-\s*\d{1,2}:\d{2}\s*[—–-]\s*",
    re.I,
)


def _sentences(text: str) -> list[str]:
    return [s.strip() for s in _SENTENCE_SPLIT.split((text or "").strip()) if len(s.strip()) > 8]


def _norm_key(s: str) -> str:
    return re.sub(r"[^\w]+", " ", (s or "").lower()).strip()


def _extract_tv_digest_stories(text: str) -> list[str]:
    t = _RBC_TV_WRAP.sub("", text or "")
    t = re.sub(r"главные\s+новости\s*[—–-].*?рбк\s*:?", "", t, flags=re.I)
    chunks = re.split(r"\s*▪\s*", t)
    stories: list[str] = []
    for chunk in chunks:
        s = _INLINE_TIMESTAMP.sub("", chunk.strip())
        s = _TIMESTAMP_BULLET.sub("", s).strip()
        s = re.sub(r"\s+", " ", s).strip(" .")
        if len(s) < 12:
            continue
        if s.lower().startswith("главные новости"):
            continue
        if _norm_key(s) in {_norm_key(x) for x in stories}:
            continue
        stories.append(s)
    return stories


def normalize_rbc_tv_roundup(text: str) -> str | None:
    """Turn RBC morning-TV timestamp digests into scannable thesis bullets."""
    raw = (text or "").strip()
    if not raw:
        return None
    if not (_RBC_TV_WRAP.search(raw) or raw.count("▪") >= 2 or _INLINE_TIMESTAMP.search(raw)):
        return None
    stories = _extract_tv_digest_stories(raw)
    if len(stories) < 2:
        return None
    headline = stories[0]
    if not headline.endswith((".", "!", "?")):
        headline = f"{headline}."
    bullets = []
    for story in stories[1:]:
        line = story.rstrip(".!? ")
        if line:
            bullets.append(f"▸ {line}.")
    if not bullets:
        bullets = [f"▸ {s.rstrip('.!? ')}." for s in stories[1:] if s.strip()]
    if not bullets:
        return None
    return f"{headline}\n\n" + "\n".join(bullets)


def strip_headline_leadin(body: str, headline: str) -> str:
    """
    Remove a body prefix that repeats the headline (common in @cb_economics / @rbc_news).

    Only complete units (line / sentence / paragraph) equal to the headline are
    dropped. A headline that is merely a truncated prefix of the first sentence
    must NOT trigger stripping — slicing there chops the story mid-thought.
    """
    b = (body or "").strip()
    h = (headline or "").strip()
    if not b or not h:
        return b
    h_key = _norm_key(h)
    if _norm_key(b) == h_key:
        return ""
    first_line = b.split("\n", 1)[0].strip()
    if _norm_key(first_line.lstrip("▸• ").rstrip(" .")) == h_key.rstrip(" ."):
        return b.split("\n", 1)[1].strip() if "\n" in b else ""
    first_para = b.split("\n\n", 1)[0]
    if _norm_key(first_para) == h_key:
        return b.split("\n\n", 1)[1].strip() if "\n\n" in b else ""
    sents = [s.strip() for s in _SENTENCE_SPLIT.split(b) if s.strip()]
    if len(sents) >= 2 and _norm_key(sents[0].lstrip("▸• ")) == h_key:
        rest = b[b.find(sents[0]) + len(sents[0]) :].lstrip(" .—-\n")
        if rest.strip():
            return rest.strip()
    return b


def dedupe_headline_in_paragraph(text: str) -> str:
    """
    RBC-style posts often repeat the headline as the first words of the body
    in the same paragraph: «Title sentence Title sentence continues…»
    """
    t = (text or "").strip()
    if not t:
        return t
    if "\n\n" in t:
        parts = [p.strip() for p in t.split("\n\n") if p.strip()]
        if len(parts) >= 2:
            h0, h1 = _norm_key(parts[0]), _norm_key(parts[1])
            if h1.startswith(h0) or (len(h0) > 20 and h0 in h1[: len(h1) // 2]):
                return f"{parts[0]}\n\n{parts[1]}"
        return t

    words = t.split()
    if len(words) < 10:
        return t
    for n in range(5, len(words) - 4):
        if words[n : n + 2] == words[:2]:
            left = " ".join(words[:n]).strip()
            right = " ".join(words[n:]).strip()
            if left and right:
                return f"{left}\n\n{right}"
    sents = _sentences(t)
    if len(sents) >= 2:
        h0 = _norm_key(sents[0])
        h1 = _norm_key(sents[1])
        if h1.startswith(h0) or (len(h0) > 24 and h0 in h1):
            return f"{sents[0]}\n\n{' '.join(sents[1:])}".strip()
    return t


def merge_soft_linebreaks(text: str) -> str:
    """Join lines broken mid-sentence (common in @rbc_news copies)."""
    lines = (text or "").splitlines()
    if len(lines) < 2:
        return (text or "").strip()
    out: list[str] = []
    buf = ""
    for raw in lines:
        line = raw.strip()
        if not line:
            if buf:
                out.append(buf)
                buf = ""
            continue
        if not buf:
            buf = line
            continue
        if buf.endswith(("-", "—")):
            buf = buf[:-1] + line
            continue
        if re.search(r"[.!?…]$", buf):
            out.append(buf)
            buf = line
            continue
        if line and line[0].islower():
            buf = f"{buf} {line}"
            continue
        out.append(buf)
        buf = line
    if buf:
        out.append(buf)
    return "\n\n".join(out)


def strip_source_editorial_labels(text: str) -> str:
    t = _INLINE_LABEL.sub("\n", text or "")
    lines: list[str] = []
    for ln in t.splitlines():
        s = ln.strip()
        if not s:
            continue
        s = _SOURCE_LABEL.sub("", s).strip()
        if s:
            lines.append(s)
    return "\n".join(lines)


_INLINE_EMOJI = re.compile(r"[\U0001F300-\U0001FAFF\u2600-\u27BF\uFE0F\u200d☀⚡🔥📌]+")

_INLINE_THESIS_BULLET = re.compile(r"[ \t]+▸[ \t]+")


def resplit_inline_thesis_bullets(text: str) -> str:
    """Undo whitespace-flattening of «headline ▸ bullet» — ▸ is ours, always line-start."""
    t = text or ""
    if "▸" not in t:
        return t
    return _INLINE_THESIS_BULLET.sub("\n▸ ", t)


def normalize_wire_source_text(text: str) -> str:
    """Best-effort uniform wire input from heterogeneous Telegram sources."""
    t = (text or "").strip()
    if not t:
        return ""
    tv = normalize_rbc_tv_roundup(t)
    if tv:
        t = tv
    t = _INLINE_EMOJI.sub(" ", t)
    while _LEAD_EMOJI.search(t):
        t = _LEAD_EMOJI.sub("", t, count=1).strip()
    t = _SLASH_INITIATIVE.sub(" ", t)
    t = resplit_inline_thesis_bullets(t)
    t = strip_source_editorial_labels(t)
    t = merge_soft_linebreaks(t)
    t = dedupe_headline_in_paragraph(t)
    t = _split_title_body_capital_boundary(t)
    t = re.sub(r"\n{3,}", "\n\n", t)
    return t.strip()


_DANGLING_PREPOSITION = re.compile(
    r"\b(?:и|или|а|но|на|в|во|с|со|о|об|обо|у|по|для|из|изо|к|ко|от|до|за|при|"
    r"через|над|под|без|про|между)$",
    re.I,
)


def _split_title_body_capital_boundary(text: str) -> str:
    """«Заголовок Следующее предложение» → два абзаца (RBC one-liner titles)."""
    t = (text or "").strip()
    if "\n\n" in t or len(t) < 40:
        return t
    matches = list(re.finditer(r"(?<=[а-яё])\s+(?=[А-ЯЁA-Z][а-яёa-z])", t))
    if not matches:
        return t
    for m in reversed(matches):
        left = t[: m.start()].strip()
        right = t[m.start() :].strip()
        if len(left) < 18 or len(right) < 24:
            continue
        if left.endswith((".", "!", "?")):
            continue
        # A real headline has no sentence punctuation and never ends mid-phrase
        # on a preposition/conjunction («…ETF на | BitMine» is one sentence).
        if re.search(r"[.!?]", left):
            continue
        if _DANGLING_PREPOSITION.search(left):
            continue
        return f"{left}\n\n{right}"
    return t
