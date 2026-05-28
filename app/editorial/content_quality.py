"""Detect posts that are not publishable as standalone channel text."""

from __future__ import annotations

import re

_INCOMPLETE_TEASER = re.compile(
    r"(выглядят\s+так|выглядит\s+так|смотрите\s+(ниже|выше|картин|график)|"
    r"на\s+(фото|картинке|слайде|инфографик|иллюстрации)|"
    r"продолжение\s+(ниже|в\s+канале)|читайте\s+ниже|"
    r"as\s+shown|see\s+below|details\s+below|read\s+more|in\s+the\s+chart)\s*\.?\s*$",
    re.I,
)
_DEICTIC_STUB = re.compile(r"\b(так|ниже|выше)\s*\.?\s*$", re.I)


def is_incomplete_teaser(text: str) -> bool:
    """
    Source post refers to image/chart («выглядят так») without extractable body.
    Such items must not ship as public channel posts with only a headline.
    """
    t = (text or "").strip()
    if not t:
        return True
    if _INCOMPLETE_TEASER.search(t):
        return True
    if len(t) < 200 and _DEICTIC_STUB.search(t):
        sents = [p for p in re.split(r"(?<=[.!?])\s+", t) if len(p.strip()) > 8]
        if len(sents) <= 1:
            return True
    return False
