"""Trust-first editorial assessment — corroboration, rumors, contradictions."""

from __future__ import annotations

import re
from dataclasses import asdict, dataclass
from typing import Any

from app.editorial.scoring_engine import EditorialScore
from app.editorial.source_tiers import aggregate_source_tier

_RUMOR = re.compile(
    r"(по\s+слухам|unconfirmed|слухи|insider\s+says|якобы|rumor|allegedly|"
    r"не\s+подтвержден|без\s+официальн)",
    re.I,
)
_CONTRADICTION = re.compile(
    r"(с\s+одной\s+стороны.*с\s+другой|одни\s+утверждают.*другие|"
    r"contradict|conflicting\s+reports|противоречив)",
    re.I,
)
_CONTROVERSIAL = re.compile(
    r"(санкци|sanction|войн|war\b|конфликт|geopolitic|регулятор\s+расслед|"
    r"regulatory\s+probe|политическ\w+\s+скандал|mass\s+protest)",
    re.I,
)
_REGULATORY_RUMOR = re.compile(
    r"(готовит\s+запрет|may\s+ban|рассматривает\s+запрет|considering\s+ban|"
    r"готовят\s+санкции\s+против)",
    re.I,
)
_OUTRAGE = re.compile(r"(возмущ|outrage|ярост|бешенств|rage\s+bait)", re.I)


@dataclass(frozen=True)
class EditorialTrustAssessment:
    trust_score: float
    factual_confidence: float
    corroboration_score: float
    rumor_risk: float
    controversial_escalation: bool
    source_contradiction: bool
    manual_review_required: bool
    reasons: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["reasons"] = list(self.reasons)
        return d


def _corroboration(unique_sources: int, tier: int) -> float:
    if unique_sources >= 3:
        base = 0.92
    elif unique_sources == 2:
        base = 0.78
    elif unique_sources == 1:
        base = 0.42
    else:
        base = 0.25
    if tier == 1:
        base = min(1.0, base + 0.12)
    elif tier == 2:
        base = min(1.0, base + 0.06)
    return round(base, 4)


def evaluate_editorial_trust(
    text: str,
    escore: EditorialScore,
    *,
    sources: list[str] | None = None,
    runtime_dir: str | None = None,
    source_snippets: list[str] | None = None,
) -> EditorialTrustAssessment:
    """
    Trust score drives manual review — never auto-publish weak corroboration or rumors.
    """
    sources = list(sources or [])
    unique = len({s.strip().lower() for s in sources if s.strip()})
    tier_info = aggregate_source_tier(sources, runtime_dir=runtime_dir)

    corroboration = _corroboration(unique, tier_info.tier)
    rumor_risk = 0.0
    reasons: list[str] = []

    if _RUMOR.search(text or ""):
        rumor_risk = 0.72
        reasons.append("rumor_framing")
    if _REGULATORY_RUMOR.search(text or "") and unique < 2:
        rumor_risk = max(rumor_risk, 0.65)
        reasons.append("regulatory_rumor_single_source")

    contradiction = bool(_CONTRADICTION.search(text or ""))
    if contradiction:
        reasons.append("conflicting_reports")
    if source_snippets and len(source_snippets) >= 2:
        a, b = source_snippets[0][:200].lower(), source_snippets[1][:200].lower()
        if a and b and _negation_mismatch(a, b):
            contradiction = True
            reasons.append("source_snippet_contradiction")

    controversial = bool(_CONTROVERSIAL.search(text or ""))
    if controversial:
        reasons.append("controversial_topic")

    factual = round(
        min(
            1.0,
            escore.credibility_score * 0.35
            + escore.impact_score * 0.2
            + corroboration * 0.35
            + (1.0 - rumor_risk) * 0.1,
        ),
        4,
    )

    trust = round(
        factual * 0.5 + corroboration * 0.35 + (1.0 - rumor_risk) * 0.15 - (0.15 if contradiction else 0.0),
        4,
    )
    trust = max(0.0, min(1.0, trust))

    manual = (
        trust < 0.55
        or rumor_risk >= 0.6
        or corroboration < 0.5
        or contradiction
        or (controversial and unique < 2)
        or (_OUTRAGE.search(text or "") and tier_info.tier >= 3)
    )

    return EditorialTrustAssessment(
        trust_score=trust,
        factual_confidence=factual,
        corroboration_score=corroboration,
        rumor_risk=round(rumor_risk, 4),
        controversial_escalation=controversial,
        source_contradiction=contradiction,
        manual_review_required=manual,
        reasons=tuple(dict.fromkeys(reasons)),
    )


def _negation_mismatch(a: str, b: str) -> bool:
    neg_a = bool(re.search(r"\b(не|нет|no|not|denied|refuted)\b", a))
    neg_b = bool(re.search(r"\b(не|нет|no|not|denied|refuted)\b", b))
    return neg_a != neg_b and len(set(a.split()) & set(b.split())) >= 4
