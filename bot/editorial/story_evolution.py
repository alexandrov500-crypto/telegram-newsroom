from __future__ import annotations

import re

from bot.editorial.story_types import StoryEvent, StoryEventType

_ESCALATION_RE = re.compile(
    r"\b(worsen|escalat|sanction|crash|spike|surge|invasion|strike|"
    r"missile|mobiliz|default|collapse|plunge)\b",
    re.I,
)
_REVERSAL_RE = re.compile(
    r"\b(ceasefire|withdraw|denied|overturn|revers|walk back|"
    r"rescind|halt|pause talks)\b",
    re.I,
)
_MILESTONE_RE = re.compile(
    r"\b(approved|signed|launched|elected|passed|unveiled|"
    r"listed|ipo|merger|acquired|breakthrough)\b",
    re.I,
)
_CONTRADICTION_RE = re.compile(
    r"\b(contradict|disputes|denies earlier|refutes|backtracks|"
    r"conflicting reports|false claim)\b",
    re.I,
)
_SHIFT_RE = re.compile(
    r"\b(pivot|replaces|new strategy|reshuffle|policy shift|"
    r"unexpected turn)\b",
    re.I,
)


def detect_story_event(
    *,
    title: str,
    summary: str | None,
    prior_summary: str | None,
    importance_delta: float,
) -> StoryEvent:
    text = f"{title} {summary or ''}".strip()
    event_type = StoryEventType.UPDATE
    significance = 0.45 + min(0.35, max(0.0, importance_delta))

    if _CONTRADICTION_RE.search(text):
        event_type = StoryEventType.CONTRADICTION
        significance = max(significance, 0.72)
    elif _REVERSAL_RE.search(text):
        event_type = StoryEventType.REVERSAL
        significance = max(significance, 0.78)
    elif _ESCALATION_RE.search(text):
        event_type = StoryEventType.ESCALATION
        significance = max(significance, 0.82)
    elif _MILESTONE_RE.search(text):
        event_type = StoryEventType.MILESTONE
        significance = max(significance, 0.85)
    elif _SHIFT_RE.search(text):
        event_type = StoryEventType.SHIFT
        significance = max(significance, 0.7)
    elif prior_summary and summary:
        overlap = len(set(prior_summary.lower().split()) & set(summary.lower().split()))
        if overlap < max(4, len(prior_summary.split()) // 5):
            event_type = StoryEventType.SHIFT
            significance = max(significance, 0.58)

    significance = min(0.98, max(0.2, significance))
    return StoryEvent(
        type=event_type.value,
        significance=significance,
        headline=title[:240],
        summary=(summary or "")[:420] or None,
    )


def is_escalation(event_type: str) -> bool:
    return event_type in (
        StoryEventType.ESCALATION.value,
        StoryEventType.MILESTONE.value,
    )
