"""Explainable reason codes + human-readable rendering."""

from __future__ import annotations

from editorial.scoring.base import PRIORITY_HIGH_THRESHOLD, PRIORITY_MEDIUM_THRESHOLD, level_label
from editorial.scoring.models import EditorialIntelligenceScores, ScoringInput

# Stable taxonomy for analytics (never use raw text as metric labels).
REASON_CATALOG: dict[str, str] = {
    "multi_source_confirmation": "multi-source confirmation",
    "high_semantic_novelty": "high semantic novelty",
    "low_novelty_vs_recent": "low novelty vs recent drafts",
    "trusted_source": "trusted source",
    "low_source_trust": "mixed or low source trust",
    "large_active_cluster": "large active cluster",
    "moderate_cluster_depth": "moderate cluster depth",
    "duplicate_risk_elevated": "duplicate risk elevated",
    "low_duplicate_overlap": "low duplicate overlap",
    "cross_source_convergence": "cross-source convergence",
    "strong_language_quality": "strong language quality heuristics",
    "weak_language_quality": "weak language quality heuristics",
    "publication_priority_elevated": "publication priority elevated",
    "editorial_priority_escalation": "editorial priority escalation",
}


def render_reason_labels(codes: list[str]) -> list[str]:
    out: list[str] = []
    for code in codes:
        label = REASON_CATALOG.get(code)
        if label:
            out.append(label)
    return out


def build_explainability(
    inp: ScoringInput,
    scores: EditorialIntelligenceScores,
) -> tuple[list[str], list[str]]:
    """Return ``(reason_codes, human_reasons)``."""
    codes: list[str] = []

    if inp.unique_channel_count >= 2:
        codes.append("multi_source_confirmation")
    if scores.novelty_score >= 0.65:
        codes.append("high_semantic_novelty")
    elif scores.novelty_score <= 0.35:
        codes.append("low_novelty_vs_recent")

    if scores.source_trust_score >= 0.65:
        codes.append("trusted_source")
    elif scores.source_trust_score <= 0.4:
        codes.append("low_source_trust")

    if inp.cluster_size >= 6:
        codes.append("large_active_cluster")
    elif inp.cluster_size >= 3:
        codes.append("moderate_cluster_depth")

    if scores.duplicate_confidence >= 0.55:
        codes.append("duplicate_risk_elevated")
    elif scores.duplicate_confidence <= 0.25:
        codes.append("low_duplicate_overlap")

    if inp.source_convergence >= 0.55:
        codes.append("cross_source_convergence")

    q_lvl = level_label(scores.quality_score)
    if q_lvl == "high":
        codes.append("strong_language_quality")
    elif q_lvl == "low":
        codes.append("weak_language_quality")

    pub_pri = inp.publication_priority or {}
    if str(pub_pri.get("label") or "").lower() in ("high", "urgent"):
        codes.append("publication_priority_elevated")

    brk = inp.editorial_priority or {}
    if str(brk.get("priority_level") or "").lower() in ("high", "urgent", "critical"):
        codes.append("editorial_priority_escalation")

    seen: set[str] = set()
    deduped: list[str] = []
    for c in codes:
        if c not in seen:
            seen.add(c)
            deduped.append(c)
    deduped = deduped[:12]
    return deduped, render_reason_labels(deduped)


# Backward-compatible alias
def build_explainability_reasons(
    inp: ScoringInput,
    scores: EditorialIntelligenceScores,
) -> list[str]:
    _, labels = build_explainability(inp, scores)
    return labels
