"""Newsroom tone — calm, factual, non-hyperbolic."""

from __future__ import annotations

import re
from dataclasses import dataclass

_HYPERBOLIC = re.compile(
    r"(шокирующ|невероятн|сенсаци|катастроф|коллапс|апокалипс|"
    r"you\s+won't\s+believe|mind[-\s]?blowing|explod(e|ing)|"
    r"эксклюзивно\s+для\s+вас|срочно\s+узнай)",
    re.I,
)
_CLICKBAIT_VERBS = re.compile(
    r"(узнай|узнайте|смотри|watch\s+now|click\s+here|жми|подписывайся)",
    re.I,
)
_URGENCY_SPAM = re.compile(r"(!!!|СРОЧНО!!!|BREAKING!!!|🔥🔥)", re.I)
_EMOTIONAL = re.compile(
    r"(ужас|кошмар|позор|возмущени|ярост|паник|страх|ужасающ)",
    re.I,
)

_REPLACEMENTS: tuple[tuple[re.Pattern[str], str], ...] = (
    (re.compile(r"\bшокирующ\w*\b", re.I), ""),
    (re.compile(r"\bсенсаци\w*\b", re.I), ""),
    (re.compile(r"\bСРОЧНО!!!\b", re.I), ""),
    (re.compile(r"\bBREAKING!!!\b", re.I), "BREAKING:"),
    (re.compile(r"!{2,}"), "!"),
)


@dataclass(frozen=True)
class ToneResult:
    text: str
    sensational_hits: int
    is_acceptable: bool

    @property
    def tone_score(self) -> float:
        return round(max(0.0, 1.0 - sensational_hits * 0.2), 3)


def count_sensational_markers(text: str) -> int:
    t = text or ""
    return sum(
        1
        for rx in (_HYPERBOLIC, _CLICKBAIT_VERBS, _URGENCY_SPAM, _EMOTIONAL)
        if rx.search(t)
    )


def apply_newsroom_tone(text: str) -> ToneResult:
    """Normalize wording for public channel — concise, calm, factual."""
    from app.editorial.tuning_loader import get_editorial_tuning

    tuning = get_editorial_tuning()
    max_hits = tuning.voice.max_sensational_hits
    t = (text or "").strip()
    if not t:
        return ToneResult("", 0, True)
    hits = count_sensational_markers(t)
    if tuning.voice.strip_tabloid:
        for rx, repl in _REPLACEMENTS:
            t = rx.sub(repl, t)
    t = re.sub(r"\s+", " ", t).strip()
    t = re.sub(r"\n{3,}", "\n\n", t)
    hits_after = count_sensational_markers(t)
    threshold = max(0, max_hits)
    return ToneResult(
        text=t,
        sensational_hits=max(hits, hits_after),
        is_acceptable=hits_after <= threshold,
    )
