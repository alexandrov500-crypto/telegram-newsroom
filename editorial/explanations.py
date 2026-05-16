"""Human-readable explanations for draft_extras / pipeline signals (editor-facing)."""

from __future__ import annotations

import html
from typing import Any


def _esc(s: str) -> str:
    return html.escape(s, quote=True)


def explain_from_draft_extras(extras: dict[str, Any] | None) -> dict[str, Any]:
    """
    Build concise, detailed, and structured explanations from ``draft_extras`` JSON dict.
    Safe for HTML when fields are escaped in ``concise_html`` / ``detailed_html``.
    """
    ex = extras or {}
    ci = ex.get("cluster_intelligence") or {}
    pd = ci.get("pipeline_decision") or {}
    ep = pd.get("editorial_pipeline") or {}
    rel = pd.get("relevance") or ep.get("relevance") or {}
    if isinstance(rel, dict) and not rel and isinstance(ep.get("relevance"), dict):
        rel = ep["relevance"]
    dup = ex.get("duplicate_intel") or {}
    conf = ex.get("editorial_confidence") or {}
    pubi = ex.get("publication_intel") or {}
    pol_notes = list(rel.get("policy_notes") or [])
    reasons = list(ep.get("reasons") or pd.get("suppression_reasons") or [])
    outcome = str(ep.get("outcome") or "")

    concise = []
    if outcome:
        concise.append(f"Pipeline outcome: {outcome}.")
    if rel.get("total") is not None:
        concise.append(f"Relevance total ≈ {rel.get('total')}.")
    if reasons:
        concise.append("Signals: " + "; ".join(str(r) for r in reasons[:6]) + ("…" if len(reasons) > 6 else ""))
    if dup.get("severity"):
        concise.append(f"Duplicate intel severity: {dup.get('severity')}.")
    esc = bool(ex.get("editorial_escalate")) or bool(pd.get("escalate_priority"))
    hold = bool(ex.get("editorial_hold")) or bool(pd.get("hold_for_review"))
    if esc:
        concise.append("Escalated for editorial attention.")
    if hold:
        concise.append("Held for review (pipeline or policy).")

    detailed_lines: list[str] = []
    if isinstance(rel, dict):
        detailed_lines.append("Relevance breakdown:")
        for k in ("freshness", "source_reputation", "topic_momentum", "entity_importance", "novelty", "duplicate_suppression", "editorial_preference_boost"):
            if k in rel:
                detailed_lines.append(f"  - {k}: {rel.get(k)}")
        if rel.get("policy_delta"):
            detailed_lines.append(f"  - policy_delta (points): {rel.get('policy_delta')}")
        if pol_notes:
            detailed_lines.append("Policy notes:")
            for n in pol_notes[:12]:
                detailed_lines.append(f"  - {n}")
    if isinstance(ep, dict) and ep.get("score_breakdown"):
        detailed_lines.append("Score breakdown (pipeline):")
        sb = ep["score_breakdown"]
        if isinstance(sb, dict):
            for k, v in list(sb.items())[:20]:
                detailed_lines.append(f"  - {k}: {v}")
    if isinstance(conf, dict) and conf:
        detailed_lines.append("Confidence:")
        for k in ("confidence_score", "publication_risk_score", "ai_quality_score", "source_agreement_score"):
            if k in conf:
                detailed_lines.append(f"  - {k}: {conf.get(k)}")
    if isinstance(pubi, dict) and pubi:
        detailed_lines.append("Publication intel snapshot:")
        detailed_lines.append(f"  {pubi!r}"[:800])

    structured = {
        "outcome": outcome or None,
        "relevance_total": rel.get("total"),
        "suppression_reasons": reasons,
        "duplicate_severity": dup.get("severity"),
        "duplicate_max_pct": dup.get("max_similarity_pct"),
        "confidence": {k: conf.get(k) for k in ("confidence_score", "publication_risk_score") if isinstance(conf, dict)},
        "policy_notes": pol_notes,
        "adaptation": ep.get("adaptation") if isinstance(ep, dict) else None,
        "escalation": esc,
        "hold_for_review": hold,
    }

    concise_txt = " ".join(concise).strip() or "No cluster intelligence on this draft (legacy or stripped extras)."
    detailed_txt = "\n".join(detailed_lines).strip() or concise_txt

    return {
        "concise": concise_txt,
        "detailed": detailed_txt,
        "concise_html": "<p>" + _esc(concise_txt) + "</p>",
        "detailed_html": "<pre>" + _esc(detailed_txt) + "</pre>",
        "structured": structured,
    }


def explain_suppression(extras: dict[str, Any] | None) -> str:
    ex = extras or {}
    ci = ex.get("cluster_intelligence") or {}
    pd = ci.get("pipeline_decision") or {}
    ep = pd.get("editorial_pipeline") or {}
    reasons = list(ep.get("reasons") or pd.get("suppression_reasons") or [])
    if not reasons:
        return "No explicit suppression reasons recorded for this draft."
    return "Suppression / gate signals:\n- " + "\n- ".join(str(r) for r in reasons)


def explain_cadence_block(reasons: list[str] | None) -> str:
    if not reasons:
        return "No cadence gate reasons supplied."
    return "Cadence:\n- " + "\n- ".join(str(r) for r in reasons)


def explain_escalation(extras: dict[str, Any] | None) -> str:
    ex = extras or {}
    ci = ex.get("cluster_intelligence") or {}
    pd = ci.get("pipeline_decision") or {}
    esc = bool(ex.get("editorial_escalate")) or bool(pd.get("escalate_priority"))
    return (
        "This draft is flagged for escalation (priority / human review)."
        if esc
        else "No escalation flag is set on this draft."
    )


def explain_confidence_summary(extras: dict[str, Any] | None) -> str:
    ex = extras or {}
    conf = ex.get("editorial_confidence") or {}
    if not isinstance(conf, dict) or not conf:
        return "No editorial confidence block stored."
    parts = []
    for k in ("confidence_score", "publication_risk_score", "ai_quality_score"):
        if k in conf:
            parts.append(f"{k}: {conf.get(k)}")
    return "; ".join(parts) if parts else "Confidence dict present but no known keys."
