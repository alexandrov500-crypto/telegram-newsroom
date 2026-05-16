from __future__ import annotations

import re
from typing import Literal

RewriteMode = Literal["short", "formal", "urgent", "neutral"]


def rewrite_draft(content: str, mode: RewriteMode) -> str:
    """
    Deterministic text transforms (no LLM). Caller may persist via repository.
    """
    raw = (content or "").strip()
    if not raw:
        return ""
    if mode == "short":
        paras = [p.strip() for p in re.split(r"\n\s*\n", raw) if p.strip()]
        head = paras[0] if paras else raw
        if len(head) > 480:
            head = head[:477].rstrip() + "…"
        return head
    if mode == "formal":
        body = raw.replace("\n\n", "\n").strip()
        return "According to compiled sources:\n\n" + body[:3500]
    if mode == "urgent":
        if not re.match(r"(?i)^(breaking|urgent)\b", raw):
            return "URGENT: " + raw[:3500]
        return raw[:3500]
    return raw[:4000]
