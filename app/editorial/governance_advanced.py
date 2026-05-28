"""Advanced governance — auto-block and sensitive-topic manual review."""

from __future__ import annotations

import re
from dataclasses import dataclass

_OUTRAGE_BAIT = re.compile(
    r"(возмущени\w*|outrage|ярост\w*|бешенств|позор\w*|разнесли\s+в\s+соц)",
    re.I,
)
_MEME_NEWS = re.compile(r"(мемкоин|meme\s+stock|dogecoin\s+pump|pepe\s+coin)", re.I)
_GOSSIP_ECON = re.compile(
    r"(сплетн\w*\s+о\s+зарплат|кто\s+спит\s+с\s+кем|развод\s+миллионер)",
    re.I,
)
_RAGE = re.compile(r"(ненавист|hate\s+campaign|lynch\s+mob|травл[аи])", re.I)
_MANUAL_GEO = re.compile(
    r"(санкци|sanction|войн|war\b|конфликт|nato|наступлени|mobilization|"
    r"геополит|regulatory\s+rumor|регулятор\s+готовит)",
    re.I,
)
_POLITICAL_CLAIM = re.compile(
    r"(президент\s+сказал|kremlin\s+said|белый\s+дом\s+заявил|"
    r"officials\s+deny|опроверг)",
    re.I,
)


@dataclass(frozen=True)
class GovernanceVerdict:
    auto_block: bool
    manual_review: bool
    reason: str


def evaluate_advanced_governance(text: str) -> GovernanceVerdict:
    t = text or ""
    if _RAGE.search(t) or _OUTRAGE_BAIT.search(t):
        return GovernanceVerdict(True, False, "rage_or_outrage_bait")
    if _MEME_NEWS.search(t):
        return GovernanceVerdict(True, False, "meme_news_hybrid")
    if _GOSSIP_ECON.search(t):
        return GovernanceVerdict(True, False, "gossip_disguised_as_economics")
    if _MANUAL_GEO.search(t) or (_POLITICAL_CLAIM.search(t) and _MANUAL_GEO.search(t)):
        return GovernanceVerdict(False, True, "geopolitics_or_sanctions")
    if _POLITICAL_CLAIM.search(t):
        return GovernanceVerdict(False, True, "politically_sensitive_claim")
    return GovernanceVerdict(False, False, "ok")
