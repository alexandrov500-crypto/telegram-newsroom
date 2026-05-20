"""Human-readable reasons for editorial intelligence scores."""

from __future__ import annotations

from editorial.scoring.base import level_label
from editorial.scoring.models import EditorialIntelligenceScores, ScoringInput


def build_explainability_reasons(
    inp: ScoringInput,
    scores: EditorialIntelligenceScores,
) -> list[str]:
    reasons: list[str] = []

    if inp.unique_channel_count >= 2:
        reasons.append("multi-source confirmation")
    if scores.novelty_score >= 0.65:
        reasons.append("high semantic novelty")
    elif scores.novelty_score <= 0.35:
        reasons.append("low novelty vs recent drafts")

    if scores.source_trust_score >= 0.65:
        reasons.append("trusted source")
    elif scores.source_trust_score <= 0.4:
        reasons.append("mixed or low source trust")

    if inp.cluster_size >= 6:
        reasons.append("large active cluster")
    elif inp.cluster_size >= 3:
        reasons.append("moderate cluster depth")

    if scores.duplicate_confidence >= 0.55:
        reasons.append("duplicate risk elevated")
    elif scores.duplicate_confidence <= 0.25:
        reasons.append("low duplicate overlap")

    if inp.source_convergence >= 0.55:
        reasons.append("cross-source convergence")

    q_lvl = level_label(scores.quality_score)
    if q_lvl == "high":
        reasons.append("strong language quality heuristics")
    elif q_lvl == "low":
        reasons.append("weak language quality heuristics")

    pub_pri = inp.publication_priority or {}
    if str(pub_pri.get("label") or "").lower() in ("high", "urgent"):
        reasons.append("publication priority elevated")

    brk = inp.editorial_priority or {}
    if str(brk.get("priority_level") or "").lower() in ("high", "urgent", "critical"):
        reasons.append("editorial priority escalation")

    # Dedupe while preserving order
    seen: set[str] = set()
    out: list[str] = []
    for r in reasons:
        key = r.strip().lower()
        if key and key not in seen:
            seen.add(key)
            out.append(r)
    return out[:12]
