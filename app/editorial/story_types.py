"""Story type labels for clustering and hierarchical rendering."""

from __future__ import annotations

import re
from enum import Enum

_MACRO = re.compile(
    r"(росстат|инфляц|gdp|cpi|ppi|macro|ставк|тариф|фискал|бюджет|ввп)",
    re.I,
)
_GEO = re.compile(
    r"(войн|санкци|nato|ukraine|украин|мерц|geopolitic|parliament|president|"
    r"ministry|минюст|дипломат)",
    re.I,
)
_FINANCE = re.compile(
    r"(банк|бирж|ipo|earnings|акци[ия]|облигац|кредит|ipo|retail|ритейл|"
    r"наличн|контрол.*банк)",
    re.I,
)
_CRYPTO = re.compile(
    r"(bitcoin|btc\b|ethereum|крипт|crypto|defi|блокчейн|токен)",
    re.I,
)
_TECH = re.compile(r"(ai\b|openai|apple|google|tech|chip|стартап|it\b)", re.I)
_DOMESTIC = re.compile(
    r"(школ|детск|фитнес|соцсет|eu\b|ес\b|жкх|город|регион|полици)",
    re.I,
)
_LIFESTYLE = re.compile(
    r"(мем|meme|lol|прикол|шутк|lifestyle|entertainment|giveaway)",
    re.I,
)
_BREAKING = re.compile(
    r"(срочно|breaking|urgent|экстренно|взрыв|attack|war\b)",
    re.I,
)


class StoryType(str, Enum):
    BREAKING = "breaking"
    MACRO = "macro"
    GEOPOLITICS = "geopolitics"
    FINANCE = "finance"
    CRYPTO = "crypto"
    DOMESTIC = "domestic"
    TECH = "tech"
    MISC = "misc"


def label_story_type(text: str, *, breaking_score: float = 0.0) -> str:
    t = text or ""
    if breaking_score >= 0.75 or _BREAKING.search(t):
        return StoryType.BREAKING.value
    if _LIFESTYLE.search(t) and not _MACRO.search(t):
        return StoryType.MISC.value
    if _GEO.search(t):
        return StoryType.GEOPOLITICS.value
    if _MACRO.search(t):
        return StoryType.MACRO.value
    if _CRYPTO.search(t):
        return StoryType.CRYPTO.value
    if _FINANCE.search(t):
        return StoryType.FINANCE.value
    if _TECH.search(t):
        return StoryType.TECH.value
    if _DOMESTIC.search(t):
        return StoryType.DOMESTIC.value
    return StoryType.MISC.value


_SECTION_TITLES = {
    StoryType.BREAKING.value: "BREAKING",
    StoryType.MACRO.value: "MACRO & POLICY",
    StoryType.GEOPOLITICS.value: "GEOPOLITICS",
    StoryType.FINANCE.value: "MARKETS & FINANCE",
    StoryType.CRYPTO.value: "CRYPTO",
    StoryType.TECH.value: "TECH & BUSINESS",
    StoryType.DOMESTIC.value: "DOMESTIC",
    StoryType.MISC.value: "OTHER",
}


def section_title(story_type: str, *, rank: int = 1) -> str:
    base = _SECTION_TITLES.get(story_type, "OTHER")
    if rank == 1 and story_type != StoryType.BREAKING.value:
        return "TOP STORIES" if rank == 1 else base
    if rank <= 3:
        return "OTHER IMPORTANT" if rank > 1 else base
    return base
