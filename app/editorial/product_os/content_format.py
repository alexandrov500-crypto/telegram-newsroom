"""Content format taxonomy — productized post types."""

from __future__ import annotations

import re
from enum import Enum

_BREAKING = re.compile(r"(breaking|срочно|urgent|record|surge|обвал|jumped)", re.I)
_DIGEST = re.compile(r"(сводк|digest|утрен|вечерн|morning|evening|wrap|итог)", re.I)
_MODEL = re.compile(r"(ментальн|mental\s+model|framework|модель|как\s+понимать|explainer)", re.I)
_INSIGHT = re.compile(r"(implication|cross.?domain|связь\s+с|insight|сигнал\s+для)", re.I)
_CONTEXT = re.compile(r"(контекст|context|почему\s+важ|why\s+it\s+matters|объясн)", re.I)


class ContentFormat(str, Enum):
    SIGNAL = "signal"
    CONTEXT = "context"
    MODEL = "model"
    DIGEST = "digest"
    INSIGHT = "insight"


def classify_content_format(
    text: str,
    *,
    is_breaking: bool = False,
    force_digest: bool = False,
    post_type: str = "",
) -> ContentFormat:
    if force_digest or post_type == "digest" or _DIGEST.search(text or ""):
        return ContentFormat.DIGEST
    if is_breaking or _BREAKING.search(text or ""):
        return ContentFormat.SIGNAL
    if _MODEL.search(text or ""):
        return ContentFormat.MODEL
    if _INSIGHT.search(text or ""):
        return ContentFormat.INSIGHT
    if _CONTEXT.search(text or ""):
        return ContentFormat.CONTEXT
    return ContentFormat.CONTEXT
