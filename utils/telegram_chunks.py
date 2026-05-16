from __future__ import annotations

import logging
import re
from typing import Final

TELEGRAM_MAX_MESSAGE_LENGTH: Final[int] = 4096
SAFE_CHUNK: Final[int] = 4000


def _is_safe_split_index(text: str, idx: int) -> bool:
    """Avoid splitting inside HTML tags or named/numeric character references."""
    if idx <= 0 or idx > len(text):
        return True
    segment = text[:idx]
    depth = 0
    for ch in segment:
        if ch == "<":
            depth += 1
        elif ch == ">":
            depth = max(0, depth - 1)
    if depth != 0:
        return False

    amp = segment.rfind("&")
    if amp == -1:
        return True
    tail = segment[amp:]
    if ";" in tail:
        return True
    if len(tail) > 96 or "\n" in tail or "\t" in tail:
        return True
    if re.match(r"^&[#a-zA-Z0-9]{1,96}$", tail):
        return False
    return True


def _find_sentence_like_cut(window: str, low: int, high: int) -> int | None:
    """Prefer newlines / sentence punctuation inside [low, high]."""
    best: int | None = None
    for needle in ("\n\n", "\n", ". ", "! ", "? ", "。"):
        pos = window.rfind(needle, low, high + 1)
        if pos != -1:
            cut = pos + len(needle)
            if best is None or cut > best:
                best = cut
    return best


def split_telegram_text(
    text: str,
    max_len: int = SAFE_CHUNK,
    *,
    respect_html: bool = False,
) -> list[str]:
    """
    Split into <= max_len chunks. Unicode-safe (str indices are codepoints).
    Prefers sentence / paragraph boundaries; optionally avoids breaking HTML.
    """
    if len(text) <= max_len:
        return [text]

    chunks: list[str] = []
    remaining = text
    while remaining:
        if len(remaining) <= max_len:
            chunks.append(remaining)
            break

        high = min(max_len, len(remaining))
        cut = high
        if respect_html:
            while cut > max_len // 3 and not _is_safe_split_index(remaining, cut):
                cut -= 1
        else:
            while cut > max_len // 3 and not _is_safe_split_index(remaining, cut):
                cut -= 1

        low = max(max_len // 3, cut - 900)
        sentence_cut = _find_sentence_like_cut(remaining, low, cut)
        if sentence_cut is not None and _is_safe_split_index(remaining, sentence_cut):
            cut = sentence_cut
        elif not _is_safe_split_index(remaining, cut):
            cut = high

        chunk = remaining[:cut].rstrip()
        if not chunk:
            chunk = remaining[: min(high, len(remaining))]
            cut = len(chunk)

        chunks.append(chunk)
        remaining = remaining[cut:].lstrip()

    return chunks
